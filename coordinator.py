"""Data coordinator for Fronius Virtual Inverter."""
from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import (
    CONF_P_AKKU_DUAL_MODE,
    CONF_P_AKKU_INVERT,
    CONF_P_AKKU_SENSOR,
    CONF_P_AKKU_SENSOR_NEG,
    CONF_P_AKKU_SENSOR_POS,
    CONF_P_GRID_DUAL_MODE,
    CONF_P_GRID_INVERT,
    CONF_P_GRID_SENSOR,
    CONF_P_GRID_SENSOR_NEG,
    CONF_P_GRID_SENSOR_POS,
    CONF_P_LOAD_INVERT,
    CONF_P_LOAD_SENSOR,
    CONF_P_PV_INVERT,
    CONF_P_PV_SENSOR,
    CONF_SOC_SENSOR,
    CONF_UPDATE_INTERVAL,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
)
from .sensor_reader import read_power_value, read_soc

_LOGGER = logging.getLogger(__name__)


class FroniusVirtualInverterCoordinator(DataUpdateCoordinator):
    """Coordinator that reads HA sensors and provides power flow data."""

    def __init__(self, hass: HomeAssistant, config: dict[str, Any]) -> None:
        self._config = config
        interval = int(config.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL))

        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=interval),
        )

        # PV energy accumulators
        self._e_day: float = 0.0
        self._e_year: float = 0.0
        self._e_total: float = 0.0

        # Grid energy accumulators for Modbus Smart Meter emulation
        self._tot_wh_imp: float = 0.0
        self._tot_wh_exp: float = 0.0

    async def _async_update_data(self) -> dict[str, Any]:
        """Read all configured sensors and return power flow data."""
        cfg = self._config

        p_grid = read_power_value(
            self.hass,
            single_sensor=cfg.get(CONF_P_GRID_SENSOR),
            pos_sensor=cfg.get(CONF_P_GRID_SENSOR_POS),
            neg_sensor=cfg.get(CONF_P_GRID_SENSOR_NEG),
            dual_mode=bool(cfg.get(CONF_P_GRID_DUAL_MODE, False)),
            invert=bool(cfg.get(CONF_P_GRID_INVERT, False)),
        )

        p_pv = read_power_value(
            self.hass,
            single_sensor=cfg.get(CONF_P_PV_SENSOR),
            pos_sensor=None,
            neg_sensor=None,
            dual_mode=False,
            invert=bool(cfg.get(CONF_P_PV_INVERT, False)),
        )

        p_akku = read_power_value(
            self.hass,
            single_sensor=cfg.get(CONF_P_AKKU_SENSOR),
            pos_sensor=cfg.get(CONF_P_AKKU_SENSOR_POS),
            neg_sensor=cfg.get(CONF_P_AKKU_SENSOR_NEG),
            dual_mode=bool(cfg.get(CONF_P_AKKU_DUAL_MODE, False)),
            invert=bool(cfg.get(CONF_P_AKKU_INVERT, False)),
        )

        p_load = read_power_value(
            self.hass,
            single_sensor=cfg.get(CONF_P_LOAD_SENSOR),
            pos_sensor=None,
            neg_sensor=None,
            dual_mode=False,
            invert=bool(cfg.get(CONF_P_LOAD_INVERT, False)),
        )

        soc = read_soc(self.hass, cfg.get(CONF_SOC_SENSOR))

        interval_s = float(int(cfg.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL)))

        # Accumulate PV energy
        if p_pv is not None and p_pv > 0:
            increment_wh = p_pv * interval_s / 3600.0
            self._e_day += increment_wh
            self._e_year += increment_wh
            self._e_total += increment_wh

        # Accumulate grid energy for Modbus meter
        if p_grid is not None:
            grid_wh = abs(p_grid) * interval_s / 3600.0
            if p_grid > 0:
                self._tot_wh_imp += grid_wh
            elif p_grid < 0:
                self._tot_wh_exp += grid_wh

        result: dict[str, Any] = {
            "P_Grid": p_grid,
            "P_PV": p_pv,
            "P_Akku": p_akku,
            "P_Load": p_load,
            "SOC": soc,
            "E_Day": self._e_day,
            "E_Year": self._e_year,
            "E_Total": self._e_total,
            "_tot_wh_imp": self._tot_wh_imp,
            "_tot_wh_exp": self._tot_wh_exp,
        }

        _LOGGER.debug(
            "Updated power flow: P_Grid=%s P_PV=%s P_Akku=%s P_Load=%s SOC=%s",
            p_grid, p_pv, p_akku, p_load, soc,
        )
        return result

    def update_config(self, new_config: dict[str, Any]) -> None:
        """Update config (called after options flow)."""
        self._config = new_config
        interval = int(new_config.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL))
        self.update_interval = timedelta(seconds=interval)
