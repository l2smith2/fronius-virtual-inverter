"""mDNS announcer for Fronius Virtual Inverter."""
from __future__ import annotations

import json
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
FRONIUS_SE_TYPE = "_Fronius-SE-Wattpilot._tcp.local."

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


def _build_fronius_se_txt(name: str, serial: str) -> dict:
    meta = {
        "DeviceMeta": {
            "Network": {
                "PrimaryNetworkInterface": "eth0"
            },
            "Device-Information": {
                "Systemname": name,
                "DeviceSerialNumber": serial,
                "DeviceGroup": "Fronius Datamanager 2.0",
                "ArticleNumber": "4,240,100",
                "CommonName": f"Datamanager_{serial}",
                "Manufacturer": "Fronius",
                "SoftwareBundleVersion": "3.4.0-102",
                "HardwareRevision": "2.0",
                "CommissioningCompleted": "true"
            },
            "Connections": []
        },
        "ZeroconfMetaVersion": "1.0"
    }
    full = json.dumps(meta, separators=(',', ':'))
    return {
        "FSED-DID": "V 1|P JSON|PFC 2",
        "00": full[:255],
        "01": full[255:],
    }


class FroniusMDNSAnnouncer:
    """Announces the virtual inverter via mDNS using HA's shared Zeroconf instance."""

    def __init__(self, name: str, port: int, serial: str) -> None:
        self._name = name
        self._port = port
        self._serial = serial
        self._zeroconf: AsyncZeroconf | None = None
        self._service_info_http: ServiceInfo | None = None
        self._service_info_se: ServiceInfo | None = None

    async def async_start(self, hass: HomeAssistant) -> None:
        """Register both mDNS services using HA's shared Zeroconf instance."""
        local_ip = _get_local_ip()
        ip_bytes = socket.inet_aton(local_ip)

        self._service_info_http = ServiceInfo(
            type_=MDNS_HTTP_TYPE,
            name=f"{self._name}.{MDNS_HTTP_TYPE}",
            addresses=[ip_bytes],
            port=self._port,
            properties=FRONIUS_TXT_RECORDS,
            server=f"{self._name}.local.",
        )

        self._service_info_se = ServiceInfo(
            type_=FRONIUS_SE_TYPE,
            name=f"{self._name}.{FRONIUS_SE_TYPE}",
            addresses=[ip_bytes],
            port=80,
            properties=_build_fronius_se_txt(self._name, self._serial),
            server=f"{self._name}.local.",
        )

        self._zeroconf = await async_get_instance(hass)
        await self._zeroconf.async_register_service(self._service_info_http)
        await self._zeroconf.async_register_service(self._service_info_se)
        _LOGGER.info(
            "mDNS: Announced '%s' at %s:%d (%s + %s)",
            self._name,
            local_ip,
            self._port,
            MDNS_HTTP_TYPE,
            FRONIUS_SE_TYPE,
        )

    async def async_stop(self) -> None:
        """Unregister both mDNS services. Does NOT close the shared Zeroconf instance."""
        if self._zeroconf:
            for info in (self._service_info_http, self._service_info_se):
                if info is not None:
                    try:
                        await self._zeroconf.async_unregister_service(info)
                    except Exception as err:
                        _LOGGER.debug("Error unregistering mDNS service: %s", err)
        _LOGGER.info("mDNS announcement stopped")
