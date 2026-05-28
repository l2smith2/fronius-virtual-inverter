"""Fronius Solar API v1 HTTP server."""
from __future__ import annotations

import asyncio
import json
import logging
import math
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from aiohttp import web

from .const import (
    API_ACTIVE_DEVICE_INFO,
    API_INVERTER_INFO,
    API_INVERTER_REALTIME,
    API_LOGGER_INFO,
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
        system_name: str,
    ) -> None:
        self._coordinator = coordinator
        self._port = port
        self._serial = serial
        self._inverter_name = inverter_name
        self._system_name = system_name
        self._app = web.Application()
        self._runner: web.AppRunner | None = None
        self._site: web.TCPSite | None = None
        self._setup_routes()

    def _setup_routes(self) -> None:
        self._app.router.add_get(API_VERSION, self._handle_api_version)
        self._app.router.add_get(API_ACTIVE_DEVICE_INFO, self._handle_active_device_info)
        self._app.router.add_get(API_POWER_FLOW, self._handle_power_flow)
        self._app.router.add_get(API_INVERTER_INFO, self._handle_inverter_info)
        self._app.router.add_get(API_INVERTER_REALTIME, self._handle_inverter_realtime)
        self._app.router.add_get(API_METER_REALTIME, self._handle_meter_realtime)
        self._app.router.add_get("/solar_api/v1/GetMeterRealtimeData.cgi", self._handle_meter_realtime)
        self._app.router.add_get(API_STORAGE_REALTIME, self._handle_storage_realtime)
        self._app.router.add_get(API_LOGGER_INFO, self._handle_logger_info)
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
            text=json.dumps(data, indent=3),
        )

    async def _handle_api_version(self, request: web.Request) -> web.Response:
        return self._json_response(
            {
                "APIVersion": 1,
                "BaseURL": "/solar_api/v1/",
                "CompatibilityRange": "1.8-1",
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

        e_day = data.get("E_Day", 0.0)
        e_year = data.get("E_Year", 0.0)
        e_total = data.get("E_Total", 0.0)

        inverter_block: dict[str, Any] = {
            "DT": 102,
            "P": round(p_pv, 1) if p_pv is not None else None,
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
            "Mode": "bidirectional" if p_akku is not None else "meter",
            "P_PV": round(p_pv, 1) if p_pv is not None else None,
            "P_Grid": round(p_grid, 1) if p_grid is not None else None,
            "P_Akku": round(p_akku, 1) if p_akku is not None else None,
        }

        if p_akku is not None:
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

    async def _handle_active_device_info(self, request: web.Request) -> web.Response:
        device_class = request.rel_url.query.get("DeviceClass", "")
        if device_class == "Meter":
            data = {"0": {"DT": -1, "Serial": self._serial}}
        else:
            data = {}
        payload = {
            "Body": {"Data": data},
            "Head": _make_head(),
        }
        return self._json_response(payload)

    async def _handle_inverter_info(self, request: web.Request) -> web.Response:
        ct_rating = self._coordinator.data.get("grid_ct_rating", 32)
        payload = {
            "Body": {
                "Data": {
                    "1": {
                        "CustomName": self._system_name,
                        "DT": FRONIUS_DEVICE_TYPE,
                        "ErrorCode": 0,
                        "PVPower": 5000,
                        "Show": 1,
                        "StatusCode": 7,  # 7 = running
                        "UniqueID": self._serial,
                        "MaxACCurrent": ct_rating,
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
        """Return grid meter data with per-phase breakdown for load balancing."""
        data = self._coordinator.data
        p_grid = data.get("P_Grid", 0.0) or 0.0
        phases = int(data.get("grid_phases", 1))
        tot_wh_imp = data.get("_tot_wh_imp", 0.0)
        tot_wh_exp = data.get("_tot_wh_exp", 0.0)

        p_a = data.get("P_Grid_A")
        p_b = data.get("P_Grid_B")
        p_c = data.get("P_Grid_C")
        i_a = data.get("I_Grid_A")
        i_b = data.get("I_Grid_B")
        i_c = data.get("I_Grid_C")
        v_a: float = data.get("V_Grid_A", 240.0)
        v_b: float = data.get("V_Grid_B", 240.0)
        v_c: float = data.get("V_Grid_C", 240.0)

        if p_a is None and p_b is None and p_c is None:
            if phases == 3:
                p_a = p_b = p_c = p_grid / 3.0
            else:
                p_a, p_b, p_c = p_grid, 0.0, 0.0
        else:
            p_a = p_a or 0.0
            p_b = p_b or 0.0
            p_c = p_c or 0.0

        i_a = i_a if i_a is not None else p_a / v_a
        i_b = i_b if i_b is not None else p_b / v_b
        i_c = i_c if i_c is not None else p_c / v_c

        pf_sensor_a = data.get("PF_Grid_A")
        pf_sensor_b = data.get("PF_Grid_B")
        pf_sensor_c = data.get("PF_Grid_C")
        q_a = data.get("Q_Grid_A") or 0.0
        q_b = data.get("Q_Grid_B") or 0.0
        q_c = data.get("Q_Grid_C") or 0.0

        def _derive_pf(p: float, i: float, v: float, sensor: float | None) -> float:
            if sensor is not None:
                return sensor
            s = i * v
            return round(p / s, 3) if s > 0 else (1.0 if p >= 0 else -1.0)

        def _apparent(p: float, q: float) -> float:
            return math.sqrt(p * p + q * q) if q != 0.0 else abs(p)

        pf_a = _derive_pf(p_a, i_a, v_a, pf_sensor_a)
        pf_b = _derive_pf(p_b, i_b, v_b, pf_sensor_b)
        pf_c = _derive_pf(p_c, i_c, v_c, pf_sensor_c)
        s_a = _apparent(p_a, q_a)
        s_b = _apparent(p_b, q_b)
        s_c = _apparent(p_c, q_c)
        q_sum = q_a + q_b + q_c
        s_sum = _apparent(p_grid, q_sum)
        pf_sum = round(p_grid / s_sum, 3) if s_sum > 0 else (1.0 if p_grid >= 0 else -1.0)

        timestamp = int(datetime.now(timezone.utc).timestamp())

        meter_data: dict = {
            "Details": {
                "Manufacturer": "Fronius",
                "Model": "Smart Meter TS 65A-3",
                "Serial": self._serial,
            },
            "Enable": 1,
            "TimeStamp": timestamp,
            "Meter_Location_Current": 0,
            "Visible": 1,
            "Frequency_Phase_Average": 50.0,
            "PowerReal_P_Sum": round(p_grid, 1),
            "PowerReactive_Q_Sum": round(q_sum, 1),
            "PowerApparent_S_Sum": round(s_sum, 1),
            "PowerFactor_Sum": pf_sum,
            "Current_AC_Sum": round(i_a if phases == 1 else i_a + i_b + i_c, 2),
            "EnergyReal_WAC_Minus_Absolute": round(tot_wh_exp, 1),
            "EnergyReal_WAC_Plus_Absolute": round(tot_wh_imp, 1),
            "EnergyReal_WAC_Sum_Consumed": round(tot_wh_imp, 1),
            "EnergyReal_WAC_Sum_Produced": round(tot_wh_exp, 1),
            # Phase 1 (always present)
            "Voltage_AC_Phase_1": round(v_a, 1),
            "Current_AC_Phase_1": round(i_a, 2),
            "PowerReal_P_Phase_1": round(p_a, 1),
            "PowerReactive_Q_Phase_1": round(q_a, 1),
            "PowerApparent_S_Phase_1": round(s_a, 1),
            "PowerFactor_Phase_1": pf_a,
            "EnergyReal_WAC_Phase_1_Consumed": round(tot_wh_imp, 1),
            "EnergyReal_WAC_Phase_1_Produced": round(tot_wh_exp, 1),
        }

        if phases == 3:
            meter_data.update({
                "Voltage_AC_Phase_2": round(v_b, 1),
                "Voltage_AC_Phase_3": round(v_c, 1),
                "Current_AC_Phase_2": round(i_b, 2),
                "Current_AC_Phase_3": round(i_c, 2),
                "PowerReal_P_Phase_2": round(p_b, 1),
                "PowerReal_P_Phase_3": round(p_c, 1),
                "PowerReactive_Q_Phase_2": round(q_b, 1),
                "PowerReactive_Q_Phase_3": round(q_c, 1),
                "PowerApparent_S_Phase_2": round(s_b, 1),
                "PowerApparent_S_Phase_3": round(s_c, 1),
                "PowerFactor_Phase_2": pf_b,
                "PowerFactor_Phase_3": pf_c,
            })

        scope = request.rel_url.query.get("Scope", "System")
        body_data: dict = {"0": meter_data}

        payload = {
            "Body": {"Data": body_data},
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

    async def _handle_logger_info(self, request: web.Request) -> web.Response:
        payload = {
            "Body": {
                "LoggerInfo": {
                    "UniqueID": f"240.{self._system_name}",
                    "ProductID": "fronius-datamanager-card",
                    "PlatformID": "wilma",
                    "HWVersion": "1.4E",
                    "SWVersion": "3.4.0-102",
                    "TimezoneLocation": "Australia/Sydney",
                    "TimezoneName": "AEST",
                    "UTCOffset": 36000,
                    "DefaultLanguage": "en",
                    "CashFactor": 0.0,
                    "CashCurrency": "AUD",
                    "CO2Factor": 0.53,
                    "CO2Unit": "kg",
                    "Systemname": self._system_name,
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
