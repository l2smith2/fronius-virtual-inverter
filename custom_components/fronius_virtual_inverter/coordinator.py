"""Data coordinator for Fronius Virtual Inverter."""
from __future__ import annotations

import logging
from time import monotonic
from datetime import datetime, timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from .const import (
    CONF_ENTRY_TYPE,
    CONF_GRID_CT_RATING,
    CONF_GRID_PHASES,
    CONF_METER_ROLE,
    CONF_MODBUS_ADDRESS,
    CONF_MODBUS_ENABLED,
    CONF_P_AKKU_CHARGE_SENSOR,
    CONF_P_AKKU_DISCHARGE_SENSOR,
    CONF_P_AKKU_INVERT,
    CONF_P_AKKU_SENSOR,
    CONF_P_GRID_EXPORT_SENSOR,
    CONF_P_GRID_IMPORT_SENSOR,
    CONF_P_GRID_INVERT,
    CONF_P_GRID_SENSOR,
    CONF_P_LOAD_INVERT,
    CONF_P_LOAD_SENSOR,
    CONF_P_PV_INVERT,
    CONF_P_PV_SENSOR,
    CONF_SOC_SENSOR,
    CONF_UPDATE_INTERVAL,
    DEFAULT_GRID_CT_RATING,
    DEFAULT_MODBUS_ADDRESS,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
    ENTRY_TYPE_METER,
    METER_ROLE_GENERATOR,
    PHASE_QUANTITIES,
    PHASES,
    phase_key,
)
from .sensor_reader import get_sensor_value, read_signed_power, read_soc

_LOGGER = logging.getLogger(__name__)

_STORAGE_VERSION = 1
_SAVE_INTERVAL = 300  # s — also saved on unload, and flushed when HA stops
_MAX_GAP = 300  # s — cap on one integration step (e.g. after the loop stalled)
_ENERGY_KEYS = ("E_Day", "E_Year", "E_Total", "_tot_wh_imp", "_tot_wh_exp")


def _energy_store(hass: HomeAssistant, entry_id: str) -> Store[dict[str, Any]]:
    return Store(hass, _STORAGE_VERSION, f"{DOMAIN}.{entry_id}")


async def async_remove_energy_store(hass: HomeAssistant, entry_id: str) -> None:
    """Delete an entry's stored energy counters."""
    await _energy_store(hass, entry_id).async_remove()


class FroniusVirtualInverterCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Reads the mapped HA sensors and keeps the energy counters."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.config: dict[str, Any] = {**entry.data, **entry.options}
        self.is_meter = self.config.get(CONF_ENTRY_TYPE) == ENTRY_TYPE_METER
        interval = int(self.config.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL))
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN} {entry.title}",
            update_interval=timedelta(seconds=interval),
        )
        self.last_refresh: datetime | None = None
        # Energy counters persist across restarts: a real meter's totals never
        # go backwards, and Fronius/SolarWeb log energy from these registers.
        self._store = _energy_store(hass, entry.entry_id)
        self._energy: dict[str, float] = dict.fromkeys(_ENERGY_KEYS, 0.0)
        self._day: str | None = None
        self._year: int | None = None
        self._last_sample: float | None = None
        self._save_due: float | None = None

    async def async_load_energy(self) -> None:
        """Restore energy counters saved by a previous run."""
        stored = await self._store.async_load() or {}
        for key in _ENERGY_KEYS:
            if isinstance(stored.get(key), (int, float)):
                self._energy[key] = float(stored[key])
        self._day = stored.get("day")
        self._year = stored.get("year")

    async def async_save_energy(self) -> None:
        """Write energy counters now (on unload)."""
        await self._store.async_save(self._energy_snapshot())

    def _energy_snapshot(self) -> dict[str, Any]:
        return {**self._energy, "day": self._day, "year": self._year}

    def _schedule_save(self) -> None:
        """Save at a fixed deadline.

        async_delay_save is a debounce — re-arming it with the same delay on
        every update would push the write back forever.
        """
        now = self.hass.loop.time()
        if self._save_due is None:
            self._save_due = now + _SAVE_INTERVAL
        elif now >= self._save_due:  # overdue: write now and start the next period
            self._save_due = now + _SAVE_INTERVAL
            self._store.async_delay_save(self._energy_snapshot, 0)
            return
        # Pending until the deadline — HA also flushes it if it stops first
        self._store.async_delay_save(self._energy_snapshot, self._save_due - now)

    async def _async_update_data(self) -> dict[str, Any]:
        """Read all configured sensors and return power flow data."""
        try:
            data = self._read_meter() if self.is_meter else self._read_inverter()
            self._integrate_energy(data)
        except Exception:
            if self.data is None:
                raise  # first refresh: let setup fail and retry
            _LOGGER.exception("Error reading sensors; serving last known values")
            return self.data
        self.last_refresh = dt_util.utcnow()
        self._schedule_save()
        _LOGGER.debug("Updated: %s", data)
        return data

    def _read_inverter(self) -> dict[str, Any]:
        cfg = self.config
        hass = self.hass
        data: dict[str, Any] = {
            "P_Grid": read_signed_power(
                hass,
                cfg.get(CONF_P_GRID_SENSOR),
                cfg.get(CONF_P_GRID_IMPORT_SENSOR),
                cfg.get(CONF_P_GRID_EXPORT_SENSOR),
                cfg.get(CONF_P_GRID_INVERT, False),
            ),
            "P_PV": read_signed_power(
                hass, cfg.get(CONF_P_PV_SENSOR), invert=cfg.get(CONF_P_PV_INVERT, False)
            ),
            # Fronius P_Akku is positive while discharging
            "P_Akku": read_signed_power(
                hass,
                cfg.get(CONF_P_AKKU_SENSOR),
                cfg.get(CONF_P_AKKU_DISCHARGE_SENSOR),
                cfg.get(CONF_P_AKKU_CHARGE_SENSOR),
                cfg.get(CONF_P_AKKU_INVERT, False),
            ),
            "P_Load": read_signed_power(
                hass, cfg.get(CONF_P_LOAD_SENSOR), invert=cfg.get(CONF_P_LOAD_INVERT, False)
            ),
            "SOC": read_soc(hass, cfg.get(CONF_SOC_SENSOR)),
            "grid_phases": 3 if cfg.get(CONF_GRID_PHASES) == "3" else 1,
            "grid_ct_rating": float(cfg.get(CONF_GRID_CT_RATING, DEFAULT_GRID_CT_RATING)),
            "modbus_address": (
                int(cfg.get(CONF_MODBUS_ADDRESS, DEFAULT_MODBUS_ADDRESS))
                if cfg.get(CONF_MODBUS_ENABLED)
                else None
            ),
        }
        # Phase B/C sensors stay configured but unused after switching to single phase
        active = PHASES[: data["grid_phases"]]
        for prefix, data_prefix in PHASE_QUANTITIES.items():
            for phase in PHASES:
                entity_id = cfg.get(phase_key(prefix, phase)) if phase in active else None
                data[f"{data_prefix}_{phase.upper()}"] = get_sensor_value(
                    hass, entity_id, fraction=prefix == "power_factor"
                )
        return data

    def _read_meter(self) -> dict[str, Any]:
        """Power through a standalone meter, in meter convention (+ = into the device)."""
        cfg = self.config
        split = bool(cfg.get(CONF_P_GRID_IMPORT_SENSOR) or cfg.get(CONF_P_GRID_EXPORT_SENSOR))
        power = read_signed_power(
            self.hass,
            cfg.get(CONF_P_GRID_SENSOR),
            cfg.get(CONF_P_GRID_IMPORT_SENSOR),
            cfg.get(CONF_P_GRID_EXPORT_SENSOR),
            cfg.get(CONF_P_GRID_INVERT, False),
        )
        # A single generator/battery sensor is entered as "+ = producing"; a
        # meter at a generator reads production as power flowing to the grid.
        if power is not None and not split and cfg.get(CONF_METER_ROLE) == METER_ROLE_GENERATOR:
            power = -power
        return {
            "P_Grid": power,
            "grid_phases": 3 if cfg.get(CONF_GRID_PHASES) == "3" else 1,
            "modbus_address": int(cfg.get(CONF_MODBUS_ADDRESS, DEFAULT_MODBUS_ADDRESS)),
        }

    def _integrate_energy(self, data: dict[str, Any]) -> None:
        """Accumulate energy over the real time elapsed since the last sample."""
        now = dt_util.now()
        if self._day != now.date().isoformat():
            self._day = now.date().isoformat()
            self._energy["E_Day"] = 0.0
        if self._year != now.year:
            self._year = now.year
            self._energy["E_Year"] = 0.0

        mono = monotonic()
        hours = 0.0 if self._last_sample is None else min(mono - self._last_sample, _MAX_GAP) / 3600
        self._last_sample = mono

        p_pv = data.get("P_PV")
        if p_pv is not None and p_pv > 0:
            for key in ("E_Day", "E_Year", "E_Total"):
                self._energy[key] += p_pv * hours
        p_grid = data.get("P_Grid")
        if p_grid is not None:
            key = "_tot_wh_imp" if p_grid > 0 else "_tot_wh_exp"
            self._energy[key] += abs(p_grid) * hours
        data.update(self._energy)
