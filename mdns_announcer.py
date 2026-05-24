"""mDNS announcer for Fronius Virtual Inverter."""
from __future__ import annotations

import logging
import socket

from zeroconf import ServiceInfo
from zeroconf.asyncio import AsyncZeroconf

_LOGGER = logging.getLogger(__name__)

# Fronius inverters advertise as _http._tcp on port 80,
# but also announce a specific Fronius service type.
# The Wattpilot's "scan for new inverters" looks for _http._tcp services
# with Fronius-specific TXT records (devicetype=fronius_datamanager_2_0 or similar).

MDNS_HTTP_TYPE = "_http._tcp.local."
FRONIUS_TXT_RECORDS = {
    "devicetype": "fronius_datamanager_2_0",
    "server": "Fronius",
}


def _get_local_ip() -> str:
    """Get the local IP address of this machine."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"


class FroniusMDNSAnnouncer:
    """Announces the virtual inverter via mDNS."""

    def __init__(self, name: str, port: int) -> None:
        self._name = name
        self._port = port
        self._zeroconf: AsyncZeroconf | None = None
        self._service_info: ServiceInfo | None = None

    async def start(self) -> None:
        """Start mDNS announcement."""
        local_ip = await _async_get_local_ip()
        ip_bytes = socket.inet_aton(local_ip)

        # Service name must be unique on the network
        service_name = f"{self._name}.{MDNS_HTTP_TYPE}"

        self._service_info = ServiceInfo(
            type_=MDNS_HTTP_TYPE,
            name=service_name,
            addresses=[ip_bytes],
            port=self._port,
            properties=FRONIUS_TXT_RECORDS,
            server=f"{self._name}.local.",
        )

        self._zeroconf = AsyncZeroconf()
        await self._zeroconf.async_register_service(self._service_info)
        _LOGGER.info(
            "mDNS: Announced '%s' at %s:%d (type: %s)",
            self._name,
            local_ip,
            self._port,
            MDNS_HTTP_TYPE,
        )

    async def stop(self) -> None:
        """Stop mDNS announcement."""
        if self._zeroconf and self._service_info:
            try:
                await self._zeroconf.async_unregister_service(self._service_info)
            except Exception as e:
                _LOGGER.debug("Error unregistering mDNS service: %s", e)
            await self._zeroconf.async_close()
        _LOGGER.info("mDNS announcement stopped")


async def _async_get_local_ip() -> str:
    """Get local IP asynchronously (runs sync call in executor via direct call)."""
    return _get_local_ip()
