"""mDNS announcer for Fronius Virtual Inverter."""
from __future__ import annotations

import asyncio
import json
import logging
import re
import socket
import struct
import subprocess
from typing import TYPE_CHECKING

from zeroconf import ServiceInfo

from homeassistant.components.zeroconf import async_get_instance
from homeassistant.core import HomeAssistant

if TYPE_CHECKING:
    from zeroconf.asyncio import AsyncZeroconf

_LOGGER = logging.getLogger(__name__)

MDNS_ADDR = "224.0.0.251"
MDNS_ADDR6 = "ff02::fb"
MDNS_PORT = 5353
MDNS_HTTP_TYPE = "_http._tcp.local."

FRONIUS_SE_INVERTER_TYPE = "_Fronius-SE-Inverter._tcp.local."
FRONIUS_SE_METER_TYPE = "_Fronius-SE-SmartMeter._tcp.local."

FRONIUS_TXT_RECORDS: dict[bytes, bytes] = {
    b"devicetype": b"fronius_datamanager_2_0",
    b"server": b"Fronius",
    b"FSED-DID": b"V 1|P JSON|PFC 2",
}

# DNS record types
_TYPE_A = 1
_TYPE_PTR = 12
_TYPE_TXT = 16
_TYPE_SRV = 33

# DNS classes
_CLASS_IN = 0x0001
_CLASS_IN_FLUSH = 0x8001  # cache-flush bit

# mDNS response flags: QR=1, Opcode=0, AA=1
_FLAGS_RESPONSE = 0x8400


def _get_local_ip() -> str:
    """Get the local IP address of this machine."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"


def _get_multicast_iface() -> str:
    """Return the interface name used to reach the mDNS multicast group."""
    try:
        result = subprocess.run(
            ["ip", "route", "get", "224.0.0.251"],
            capture_output=True, text=True, timeout=2,
        )
        match = re.search(r"\bdev\s+(\S+)", result.stdout)
        return match.group(1) if match else "eth0"
    except Exception:
        return "eth0"


# ── DNS packet helpers ────────────────────────────────────────────────────────

def _encode_name(name: str) -> bytes:
    """Encode a DNS name (e.g. 'foo._tcp.local.') to wire format."""
    result = b""
    for label in name.rstrip(".").split("."):
        enc = label.encode()
        result += bytes([len(enc)]) + enc
    return result + b"\x00"


def _rr(name: bytes, rtype: int, rclass: int, ttl: int, rdata: bytes) -> bytes:
    """Build a single DNS resource record."""
    return name + struct.pack(">HHIH", rtype, rclass, ttl, len(rdata)) + rdata


def _txt_rdata(entries: list[str]) -> bytes:
    """Encode TXT RDATA: each string is length-prefixed."""
    result = b""
    for entry in entries:
        enc = entry.encode()
        result += bytes([len(enc)]) + enc
    return result


def _build_packet(
    instance_name: str,
    service_type: str,
    hostname: str,
    port: int,
    ip_bytes: bytes,
    txt: bytes,
) -> bytes:
    """Build a complete mDNS announcement packet for one service type.

    PTR in answers (ANCOUNT=1), SRV+TXT+A in additionals (ARCOUNT=3).
    """
    svc = _encode_name(service_type)
    inst = _encode_name(f"{instance_name}.{service_type}")
    host = _encode_name(hostname)

    ptr = _rr(svc, _TYPE_PTR, _CLASS_IN, 4500, inst)
    srv = _rr(inst, _TYPE_SRV, _CLASS_IN_FLUSH, 120, struct.pack(">HHH", 0, 0, port) + host)
    txt_rr = _rr(inst, _TYPE_TXT, _CLASS_IN_FLUSH, 4500, txt)
    a_rr = _rr(host, _TYPE_A, _CLASS_IN_FLUSH, 120, ip_bytes)

    # ID=0, flags, QDCOUNT=0, ANCOUNT=1, NSCOUNT=0, ARCOUNT=3
    header = struct.pack(">HHHHHH", 0, _FLAGS_RESPONSE, 0, 1, 0, 3)
    return header + ptr + srv + txt_rr + a_rr


# ── Raw mDNS announcer (send-only, ephemeral port) ───────────────────────────

class RawMDNSAnnouncer:
    """Announces Fronius-SE service types via raw UDP multicast on IPv4 and IPv6.

    Bypasses zeroconf's 15-byte label limit by building DNS packets directly.
    Uses ephemeral source ports so it never conflicts with HA's zeroconf
    daemon on port 5353.  Send-only: no receive/query-response support.
    """

    def __init__(self, name: str, port: int, serial: str) -> None:
        self._name = name
        self._port = port
        self._serial = serial
        self._sock: socket.socket | None = None
        self._sock6: socket.socket | None = None
        self._iface: str = "eth0"
        self._packets: list[bytes] = []
        self._task: asyncio.Task | None = None

    def _make_txt(self) -> bytes:
        """Build TXT RDATA matching the Fronius device mDNS format.

        Two TXT strings:
          FSED-DID=V 1|P JSON|PFC 2
          00=<DeviceMeta JSON>   (fits in a single chunk at this size)
        Each string is length-prefixed: len(key=value) + key=value.
        """
        info = json.dumps(
            {
                "DeviceMeta": {
                    "Device-Information": {
                        "Systemname": self._name,
                        "DeviceSerialNumber": self._serial,
                        "Manufacturer": "Fronius",
                        "SoftwareBundleVersion": "3.4.0-102",
                    },
                    "ZeroconfMetaVersion": "1.0",
                },
            },
            separators=(",", ":"),
        )
        chunk = 250  # value bytes per TXT string; "00=" prefix = 253 total, within 255 limit
        entries = ["FSED-DID=V 1|P JSON|PFC 2"]
        for i, start in enumerate(range(0, len(info), chunk)):
            entries.append(f"{i:02d}={info[start : start + chunk]}")
        return _txt_rdata(entries)

    async def async_start(self) -> None:
        """Create send-only multicast sockets (IPv4 + IPv6) and start announcing."""
        local_ip = _get_local_ip()
        ip_bytes = socket.inet_aton(local_ip)
        hostname = f"{self._name}.local."
        txt = self._make_txt()

        self._packets = [
            _build_packet(self._name, svc, hostname, self._port, ip_bytes, txt)
            for svc in (FRONIUS_SE_INVERTER_TYPE, FRONIUS_SE_METER_TYPE)
        ]

        # Determine outbound interface for multicast routing
        loop = asyncio.get_running_loop()
        self._iface = await loop.run_in_executor(None, _get_multicast_iface)

        # ── IPv4 socket ───────────────────────────────────────────────────
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 255)
        self._sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_LOOP, 1)
        self._sock.setsockopt(
            socket.IPPROTO_IP,
            socket.IP_MULTICAST_IF,
            socket.inet_aton(local_ip),
        )
        self._sock.bind((local_ip, 0))
        port4 = self._sock.getsockname()[1]

        # ── IPv6 socket ───────────────────────────────────────────────────
        try:
            self._sock6 = socket.socket(socket.AF_INET6, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
            self._sock6.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_MULTICAST_HOPS, 255)
            self._sock6.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_MULTICAST_LOOP, 1)
            self._sock6.bind(("::", 0))
            port6 = self._sock6.getsockname()[1]
            _LOGGER.warning(
                "RawMDNSAnnouncer IPv6 bound on [::]:%d, iface=%s", port6, self._iface
            )
        except Exception as err:
            _LOGGER.warning("RawMDNSAnnouncer IPv6 socket failed (non-fatal): %s", err)
            self._sock6 = None
            port6 = None

        self._task = asyncio.create_task(self._announce_loop())
        _LOGGER.warning(
            "RawMDNSAnnouncer IPv4 bound to %s:%d, iface=%s, sending to 224.0.0.251:5353",
            local_ip, port4, self._iface,
        )
        _LOGGER.info(
            "Raw mDNS: announcing '%s' at %s:%d for %s and %s",
            self._name,
            local_ip,
            self._port,
            FRONIUS_SE_INVERTER_TYPE,
            FRONIUS_SE_METER_TYPE,
        )

    async def _announce_loop(self) -> None:
        iface_idx = 0
        try:
            iface_idx = socket.if_nametoindex(self._iface)
        except Exception:
            pass

        while True:
            for pkt in self._packets:
                if self._sock is not None:
                    try:
                        self._sock.sendto(pkt, (MDNS_ADDR, MDNS_PORT))
                    except Exception as err:
                        _LOGGER.debug("IPv4 mDNS send error: %s", err)
                if self._sock6 is not None:
                    try:
                        self._sock6.sendto(pkt, (MDNS_ADDR6, MDNS_PORT, 0, iface_idx))
                    except Exception as err:
                        _LOGGER.debug("IPv6 mDNS send error: %s", err)
            await asyncio.sleep(1)

    async def async_stop(self) -> None:
        """Cancel the announce loop and close sockets."""
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        if self._sock:
            self._sock.close()
            self._sock = None
        if self._sock6:
            self._sock6.close()
            self._sock6 = None
        _LOGGER.info("Raw mDNS announcer stopped")


# ── Zeroconf-based announcer (for _http._tcp.local.) ─────────────────────────

class FroniusMDNSAnnouncer:
    """Announces the virtual inverter via mDNS using HA's shared Zeroconf instance."""

    def __init__(self, name: str, port: int) -> None:
        self._name = name
        self._port = port
        self._zeroconf: AsyncZeroconf | None = None
        self._service_info: ServiceInfo | None = None

    async def async_start(self, hass: HomeAssistant) -> None:
        """Register the mDNS service using HA's shared Zeroconf instance."""
        local_ip = _get_local_ip()
        ip_bytes = socket.inet_aton(local_ip)

        self._service_info = ServiceInfo(
            type_=MDNS_HTTP_TYPE,
            name=f"{self._name}.{MDNS_HTTP_TYPE}",
            addresses=[ip_bytes],
            port=self._port,
            properties=FRONIUS_TXT_RECORDS,
            server=f"{self._name}.local.",
        )

        self._zeroconf = await async_get_instance(hass)
        await self._zeroconf.async_register_service(self._service_info)
        _LOGGER.info(
            "mDNS: Announced '%s' at %s:%d (type: %s)",
            self._name,
            local_ip,
            self._port,
            MDNS_HTTP_TYPE,
        )

    async def async_stop(self) -> None:
        """Unregister the mDNS service. Does NOT close the shared Zeroconf instance."""
        if self._service_info and self._zeroconf:
            try:
                await self._zeroconf.async_unregister_service(self._service_info)
            except Exception as err:
                _LOGGER.debug("Error unregistering mDNS service: %s", err)
        _LOGGER.info("mDNS announcement stopped")
