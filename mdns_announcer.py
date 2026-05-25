"""mDNS announcer for Fronius Virtual Inverter."""
from __future__ import annotations

import logging
import socket
from typing import TYPE_CHECKING

from zeroconf import ServiceInfo

from homeassistant.components.zeroconf import async_get_instance
from homeassistant.core import HomeAssistant

if TYPE_CHECKING:
    from zeroconf.asyncio import AsyncZeroconf

_LOGGER = logging.getLogger(__name__)

MDNS_HTTP_TYPE = "_http._tcp.local."

FRONIUS_TXT_RECORDS: dict[bytes, bytes] = {
    b"devicetype": b"fronius_datamanager_2_0",
    b"server": b"Fronius",
    b"FSED-DID": b"V 1|P JSON|PFC 2",
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
