"""Fronius Solar API v1 HTTP server."""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from aiohttp import web

from .const import (
    API_INVERTER_INFO,
    API_INVERTER_REALTIME,
    API_METER_REALTIME,
    API_POWER_FLOW,
    API_STORAGE_REALTIME,
    API_VERSION,
    FRONIUS_DEVICE_TYPE,
    FRONIUS_HARDWARE_VERSION,
    FRONIUS_SOFTWARE_VERSION,
)

if TYPE_CHECKING:
    from . import FroniusVirtualInverterCoordinator

_LOGGER = logging.getLogger(__name__)


def _make_head(timestamp: str | None = None) -> dict:
    if timestamp is None:
        timestamp = datetime.now(timezone.utc).astimezone().isoformat()
    return {
        "RequestArguments": {},
        "Status": {"Code": 0, "Reason": "", "UserMessage": ""},
        "Timestamp": timestamp,
    }


class FroniusSolarAPIServer:
    """Minimal Fronius Solar API v1 HTTP server."""

    def __init__(
        self,
        coordinator: "FroniusVirtualInverterCoordinator",
        port: int,
        serial: str,
        inverter_name: str,
    ) -> None:
        self._coordinator = coordinator
        self._port = port
        self._serial = serial
        self._inverter_name = inverter_name
        self._app = web.Application()
        self._runner: web.AppRunner | None = None
        self._site: web.TCPSite | None = None
        self._setup_routes()

    def _setup_routes(self) -> None:
        self._app.router.add_get(API_VERSION, self._handle_api_version)
        self._app.router.add_get(API_POWER_FLOW, self._handle_power_flow)
        self._app.router.add_get(API_INVERTER_INFO, self._handle_inverter_info)
        self._app.router.add_get(API_INVERTER_REALTIME, self._handle_inverter_realtime)
        self._app.router.add_get(API_METER_REALTIME, self._handle_meter_realtime)
        self._app.router.add_get(API_STORAGE_REALTIME, self._handle_storage_realtime)
        # Catch-all for any other Solar API paths
        self._app.router.add_get("/solar_api/{tail:.*}", self._handle_unknown)

    async def start(self) -> None:
        """Start the HTTP server."""
        self._runner = web.AppRunner(self._app, access_log=None)
        await self._runner.setup()
        self._site = web.TCPSite(self._runner, "0.0.0.0", self._port)
        await self._site.start()
        _LOGGER.info(
            "Fronius Virtual Inverter HTTP server started on port %d", self._port
        )

    async def stop(self) -> None:
        """Stop the HTTP server."""
        if self._site:
            await self._site.stop()
        if self._runner:
            await self._runner.cleanup()
        _LOGGER.info("Fronius Virtual Inverter HTTP server stopped")

    def _json_response(self, data: Any) -> web.Response:
        return web.Response(
            content_type="application/json",
            text=json.dumps(data, separators=(",", ":")),
        )

    async def _handle_api_version(self, request: web.Request) -> web.Response:
        return self._json_response(
            {
                "APIVersion": 1,
                "BaseURL": "/solar_api/v1/",
                "CompatibilityRange": "1.5-1",
            }
        )

    async def _handle_power_flow(self, request: web.Request) -> web.Response:
        data = self._coordinator.data
        timestamp = datetime.now(timezone.utc).astimezone().isoformat()

        p_pv = data.get("P_PV")
        p_grid = data.get("P_Grid")
        p_akku = data.get("P_Akku")
        p_load = data.get("P_Load")
        soc = data.get("SOC")

        # Inverter power = PV power (what GEN24 reports as its own output)
        inverter_p = p_pv if p_pv is not None else 0.0

        # Build E_Day / E_Year / E_Total from coordinator accumulated values
        e_day = data.get("E_Day", 0.0)
        e_year = data.get("E_Year", 0.0)
        e_total = data.get("E_Total", 0.0)

        inverter_block: dict[str, Any] = {
            "DT": FRONIUS_DEVICE_TYPE,
            "P": round(inverter_p, 1),
            "E_Day": round(e_day, 1),
            "E_Year": round(e_year, 1),
            "E_Total": round(e_total, 1),
        }
        if soc is not None:
            inverter_block["SOC"] = round(soc, 1)
            inverter_block["Battery_Mode"] = "normal"

        site_block: dict[str, Any] = {
            "E_Day": round(e_day, 1),
            "E_Year": round(e_year, 1),
            "E_Total": round(e_total, 1),
            "Meter_Location": "grid",
            "Mode": "bidirectional" if p_akku is not None else "produce-only",
        }

        if p_pv is not None:
            site_block["P_PV"] = round(p_pv, 1)
        if p_grid is not None:
            site_block["P_Grid"] = round(p_grid, 1)
        if p_akku is not None:
            site_block["P_Akku"] = round(p_akku, 1)
            site_block["BatteryStandby"] = False
            site_block["BackupMode"] = False
        if p_load is not None:
            site_block["P_Load"] = round(p_load, 1)

        # Autonomy & self-consumption
        if p_pv is not None and p_load is not None and p_load < 0:
            load_abs = abs(p_load)
            if load_abs > 0:
                self_consumption = min(p_pv / load_abs * 100, 100.0)
                site_block["rel_SelfConsumption"] = round(self_consumption, 1)
            if p_grid is not None and p_grid <= 0:
                site_block["rel_Autonomy"] = 100.0
            elif p_grid is not None and load_abs > 0:
                autonomy = max(0.0, (1 - p_grid / load_abs) * 100)
                site_block["rel_Autonomy"] = round(autonomy, 1)

        payload = {
            "Body": {
                "Data": {
                    "Inverters": {"1": inverter_block},
                    "Site": site_block,
                    "Version": "12",
                }
            },
            "Head": _make_head(timestamp),
        }
        return self._json_response(payload)

    async def _handle_inverter_info(self, request: web.Request) -> web.Response:
        payload = {
            "Body": {
                "Data": {
                    "1": {
                        "CustomName": self._inverter_name,
                        "DT": FRONIUS_DEVICE_TYPE,
                        "ErrorCode": 0,
                        "PVPower": 5000,
                        "Show": 1,
                        "StatusCode": 7,  # 7 = running
                        "UniqueID": self._serial,
                    }
                }
            },
            "Head": _make_head(),
        }
        return self._json_response(payload)

    async def _handle_inverter_realtime(self, request: web.Request) -> web.Response:
        data = self._coordinator.data
        p_pv = data.get("P_PV", 0.0) or 0.0

        payload = {
            "Body": {
                "Data": {
                    "PAC": {"Value": round(p_pv, 1), "Unit": "W"},
                    "SAC": {"Value": round(p_pv, 1), "Unit": "VA"},
                    "DAY_ENERGY": {"Value": round(data.get("E_Day", 0.0), 1), "Unit": "Wh"},
                    "YEAR_ENERGY": {"Value": round(data.get("E_Year", 0.0), 1), "Unit": "Wh"},
                    "TOTAL_ENERGY": {"Value": round(data.get("E_Total", 0.0), 1), "Unit": "Wh"},
                }
            },
            "Head": _make_head(),
        }
        return self._json_response(payload)

    async def _handle_meter_realtime(self, request: web.Request) -> web.Response:
        """Return grid meter data."""
        data = self._coordinator.data
        p_grid = data.get("P_Grid", 0.0) or 0.0

        payload = {
            "Body": {
                "Data": {
                    "0": {
                        "Details": {
                            "Manufacturer": "Fronius",
                            "Model": "Smart Meter TS 65A-3",
                            "Serial": self._serial,
                        },
                        "Enable": 1,
                        "PowerReal_P_Sum": round(p_grid, 1),
                        "Meter_Location_Current": 0,
                        "Visible": 1,
                    }
                }
            },
            "Head": _make_head(),
        }
        return self._json_response(payload)

    async def _handle_storage_realtime(self, request: web.Request) -> web.Response:
        """Return battery/storage data."""
        data = self._coordinator.data
        soc = data.get("SOC")
        p_akku = data.get("P_Akku")

        if soc is None and p_akku is None:
            # No battery configured
            payload = {
                "Body": {"Data": {}},
                "Head": _make_head(),
            }
            return self._json_response(payload)

        payload = {
            "Body": {
                "Data": {
                    "0": {
                        "Controller": {
                            "Capacity_Maximum": 10000,
                            "Current_DC": 0.0,
                            "Details": {
                                "Manufacturer": "BYD",
                                "Model": "Battery-Box Premium HVS",
                                "Serial": self._serial,
                            },
                            "Enable": 1,
                            "StateOfCharge_Relative": round(soc, 1) if soc is not None else 0.0,
                            "Status_BatteryCell": "normal",
                            "Temperature_Cell": 25.0,
                            "Voltage_DC": 400.0,
                        },
                        "Modules": [],
                    }
                }
            },
            "Head": _make_head(),
        }
        return self._json_response(payload)

    async def _handle_unknown(self, request: web.Request) -> web.Response:
        _LOGGER.debug("Unknown Solar API request: %s", request.path)
        payload = {
            "Body": {"Data": {}},
            "Head": _make_head(),
        }
        return self._json_response(payload)
