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


def _decode_name(data: bytes, offset: int) -> tuple[str, int]:
    """Decode a DNS name from wire format, following compression pointers."""
    labels: list[str] = []
    while offset < len(data):
        length = data[offset]
        if length == 0:
            offset += 1
            break
        if (length & 0xC0) == 0xC0:
            pointer = ((length & 0x3F) << 8) | data[offset + 1]
            suffix, _ = _decode_name(data, pointer)
            labels.append(suffix.rstrip("."))
            offset += 2
            return ".".join(labels) + ".", offset
        offset += 1
        labels.append(data[offset : offset + length].decode("ascii", errors="replace"))
        offset += length
    return ".".join(labels) + ".", offset


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


# ── Raw mDNS protocol / socket ────────────────────────────────────────────────

class _MDNSProtocol(asyncio.DatagramProtocol):
    """asyncio DatagramProtocol that handles mDNS sends and query responses."""

    def __init__(self, packets: list[bytes], service_types: set[str]) -> None:
        self._packets = packets
        self._service_types = service_types  # lowercased, no trailing dot
        self._transport: asyncio.DatagramTransport | None = None

    def connection_made(self, transport: asyncio.BaseTransport) -> None:
        self._transport = transport  # type: ignore[assignment]

    def send_all(self) -> None:
        if self._transport is None:
            return
        for pkt in self._packets:
            self._transport.sendto(pkt, (MDNS_ADDR, MDNS_PORT))

    def datagram_received(self, data: bytes, addr: tuple[str, int]) -> None:
        if len(data) < 12:
            return
        try:
            _id, flags, qdcount = struct.unpack_from(">HHH", data, 0)
        except struct.error:
            return
        if flags & 0x8000:  # ignore responses
            return

        offset = 12
        for _ in range(qdcount):
            if offset >= len(data):
                break
            try:
                name, offset = _decode_name(data, offset)
                qtype, _qclass = struct.unpack_from(">HH", data, offset)
                offset += 4
            except Exception:
                break
            if qtype == _TYPE_PTR and name.lower().rstrip(".") in self._service_types:
                self.send_all()
                return

    def error_received(self, exc: Exception) -> None:
        _LOGGER.debug("mDNS socket error: %s", exc)

    def connection_lost(self, exc: Exception | None) -> None:
        pass


class RawMDNSAnnouncer:
    """Announces Fronius-SE service types via raw UDP multicast.

    Bypasses zeroconf's 15-byte label limit by building DNS packets directly.
    Announces both _Fronius-SE-Inverter._tcp.local. and
    _Fronius-SE-SmartMeter._tcp.local. every 1 second, and responds to
    incoming PTR queries for those types.
    """

    def __init__(self, name: str, port: int, serial: str) -> None:
        self._name = name
        self._port = port
        self._serial = serial
        self._transport: asyncio.DatagramTransport | None = None
        self._protocol: _MDNSProtocol | None = None
        self._task: asyncio.Task | None = None

    def _make_txt(self, local_ip: str) -> bytes:
        """Build TXT RDATA: FSED-DID + device info JSON split into 00/01 chunks."""
        info = json.dumps(
            {
                "devicetype": "fronius_datamanager_2_0",
                "hostname": f"{self._name}.local",
                "serial": self._serial,
                "uniqueid": f"240.{self._serial}",
                "ip": local_ip,
                "platform": "wilma",
            },
            separators=(",", ":"),
        )
        entries = ["FSED-DID=V 1|P JSON|PFC 2"]
        chunk = 249  # 3-byte key prefix "00=" leaves 252 bytes; 249 is safe
        for i, start in enumerate(range(0, len(info), chunk)):
            entries.append(f"{i:02d}={info[start : start + chunk]}")
        return _txt_rdata(entries)

    async def async_start(self) -> None:
        """Create the multicast socket and start announcing."""
        local_ip = _get_local_ip()
        ip_bytes = socket.inet_aton(local_ip)
        hostname = f"{self._name}.local."
        txt = self._make_txt(local_ip)

        service_types = [FRONIUS_SE_INVERTER_TYPE, FRONIUS_SE_METER_TYPE]
        packets = [
            _build_packet(self._name, svc, hostname, self._port, ip_bytes, txt)
            for svc in service_types
        ]

        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
        except AttributeError:
            pass
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 255)
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_LOOP, 1)
        sock.bind(("", MDNS_PORT))
        mreq = socket.inet_aton(MDNS_ADDR) + socket.inet_aton("0.0.0.0")
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
        sock.setblocking(False)

        svc_set = {s.lower().rstrip(".") for s in service_types}
        self._protocol = _MDNSProtocol(packets, svc_set)

        loop = asyncio.get_running_loop()
        self._transport, _ = await loop.create_datagram_endpoint(
            lambda: self._protocol,
            sock=sock,
        )

        self._task = asyncio.create_task(self._announce_loop())
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
            if self._protocol is not None:
                self._protocol.send_all()
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
        if self._transport:
            self._transport.close()
            self._transport = None
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
