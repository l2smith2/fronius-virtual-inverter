"""mDNS announcer for Fronius Virtual Inverter."""
from __future__ import annotations

import asyncio
import json
import logging
import socket
import struct
from typing import TYPE_CHECKING

from zeroconf import ServiceInfo

from homeassistant.components.zeroconf import async_get_instance
from homeassistant.core import HomeAssistant

from .const import FRONIUS_HARDWARE_VERSION, FRONIUS_SOFTWARE_VERSION

if TYPE_CHECKING:
    from zeroconf.asyncio import AsyncZeroconf

_LOGGER = logging.getLogger(__name__)

MDNS_ADDR = "224.0.0.251"
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
    """Announces Fronius-SE service types via raw UDP multicast.

    Bypasses zeroconf's 15-byte label limit by building DNS packets directly.
    Uses an ephemeral source port so it never conflicts with HA's zeroconf
    daemon on port 5353.  Send-only: no receive/query-response support.
    """

    def __init__(self, name: str, port: int, serial: str) -> None:
        self._name = name
        self._port = port
        self._serial = serial
        self._sock: socket.socket | None = None
        self._packets: list[bytes] = []
        self._task: asyncio.Task | None = None

    def _make_txt(self, local_ip: str) -> bytes:
        """Build TXT RDATA matching the Fronius device mDNS format from pcap.

        Three TXT strings:
          FSED-DID=V 1|P JSON|PFC 2
          00=<first 250 bytes of DeviceMeta JSON>
          01=<remainder of DeviceMeta JSON>
        Each string is length-prefixed: len(key=value) + key=value.
        """
        info = json.dumps(
            {
                "DeviceMeta": {
                    "Network": {
                        "PrimaryNetworkInterface": "eth0",
                    },
                    "Device-Information": {
                        "Systemname": self._name,
                        "DeviceSerialNumber": self._serial,
                        "DeviceGroup": "Fronius GEN24 6.0 Plus",
                        "ArticleNumber": "4,210,209",
                        "CommonName": self._name,
                        "Manufacturer": "Fronius",
                        "SoftwareBundleVersion": FRONIUS_SOFTWARE_VERSION,
                        "HardwareRevision": FRONIUS_HARDWARE_VERSION,
                        "CommissioningCompleted": "true",
                    },
                    "Connections": [],
                },
                "ZeroconfMetaVersion": "1.0",
            },
            separators=(",", ":"),
        )
        chunk = 250  # value bytes per TXT string; "00=" prefix = 253 total, within 255 limit
        entries = ["FSED-DID=V 1|P JSON|PFC 2"]
        for i, start in enumerate(range(0, len(info), chunk)):
            entries.append(f"{i:02d}={info[start : start + chunk]}")
        return _txt_rdata(entries)

    async def async_start(self) -> None:
        """Create the send-only multicast socket and start announcing."""
        local_ip = _get_local_ip()
        ip_bytes = socket.inet_aton(local_ip)
        hostname = f"{self._name}.local."
        txt = self._make_txt(local_ip)

        self._packets = [
            _build_packet(self._name, svc, hostname, self._port, ip_bytes, txt)
            for svc in (FRONIUS_SE_INVERTER_TYPE, FRONIUS_SE_METER_TYPE)
        ]

        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 255)
        self._sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_LOOP, 1)
        self._sock.setsockopt(
            socket.IPPROTO_IP,
            socket.IP_MULTICAST_IF,
            socket.inet_aton(local_ip),
        )
        self._sock.bind((local_ip, 0))
        assigned_port = self._sock.getsockname()[1]

        self._task = asyncio.create_task(self._announce_loop())
        _LOGGER.warning(
            "RawMDNSAnnouncer bound to %s:%d, sending to 224.0.0.251:5353",
            local_ip,
            assigned_port,
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
        while True:
            if self._sock is not None:
                for pkt in self._packets:
                    self._sock.sendto(pkt, (MDNS_ADDR, MDNS_PORT))
            await asyncio.sleep(1)

    async def async_stop(self) -> None:
        """Cancel the announce loop and close the socket."""
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
