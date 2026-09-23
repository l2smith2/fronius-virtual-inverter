"""Fronius Virtual Inverter — Home Assistant custom integration.

One integration, two kinds of config entry:

  Virtual inverter (entry_type "inverter")
    Fronius Solar API v1 HTTP server + mDNS, so a Fronius Wattpilot can pair
    with Home Assistant as if it were a GEN24 and do PV surplus (Eco) charging.
    Optionally also serves the grid values as a Smart Meter IP (Modbus TCP)
    for a real Fronius inverter.

  Virtual smart meter (entry_type "meter")
    A standalone Smart Meter IP (Modbus TCP) for a real Fronius inverter —
    e.g. a secondary meter at the "external generator" position whose power
    is an AC-coupled battery.

All Modbus meters share one TCP server per port and are routed by unit ID.
"""
from __future__ import annotations

import hashlib
import logging
from functools import partial
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_NAME, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from .const import (
    CONF_ENTRY_TYPE,
    CONF_MODBUS_ADDRESS,
    CONF_MODBUS_ENABLED,
    CONF_MODBUS_PORT,
    CONF_P_AKKU_CHARGE_SENSOR,
    CONF_P_AKKU_DISCHARGE_SENSOR,
    CONF_P_AKKU_INVERT,
    CONF_P_AKKU_SENSOR,
    CONF_P_GRID_EXPORT_SENSOR,
    CONF_P_GRID_IMPORT_SENSOR,
    CONF_PORT,
    CONF_SYSTEM_NAME,
    DEFAULT_MODBUS_ADDRESS,
    DEFAULT_MODBUS_PORT,
    DEFAULT_PORT,
    ENTRY_TYPE_INVERTER,
)
from .coordinator import FroniusVirtualInverterCoordinator, async_remove_energy_store
from .http_server import FroniusSolarAPIServer
from .mdns_announcer import FroniusMDNSAnnouncer, RawMDNSAnnouncer
from .modbus_server import SunSpecMeter, async_add_meter, async_remove_meter

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR]

type FroniusConfigEntry = ConfigEntry[FroniusVirtualInverterCoordinator]


def entry_serial(entry: ConfigEntry) -> str:
    """Serial reported on every protocol.

    The display name, so the Wattpilot pairing screen shows e.g.
    "MyHome (192.168.1.x)"; falls back to a stable hash of the entry ID.
    """
    config = {**entry.data, **entry.options}
    name = config.get(CONF_SYSTEM_NAME) or config.get(CONF_NAME) or entry.title
    return name or hashlib.md5(entry.entry_id.encode()).hexdigest()[:8].upper()


async def async_setup_entry(hass: HomeAssistant, entry: FroniusConfigEntry) -> bool:
    """Set up a virtual inverter or virtual smart meter."""
    config = {**entry.data, **entry.options}
    serial = entry_serial(entry)

    coordinator = FroniusVirtualInverterCoordinator(hass, entry)
    await coordinator.async_load_energy()
    await coordinator.async_config_entry_first_refresh()
    entry.async_on_unload(coordinator.async_save_energy)

    # on_unload callbacks also run when setup fails part-way, so each service
    # registers its stop as soon as it is running.
    if coordinator.is_meter:
        try:
            await _async_start_meter(hass, entry, coordinator, serial, config)
        except (OSError, ValueError) as err:
            raise ConfigEntryNotReady(f"Cannot serve the Modbus meter: {err}") from err
    else:
        await _async_start_inverter(hass, entry, coordinator, serial, config)

    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def _async_start_inverter(
    hass: HomeAssistant,
    entry: FroniusConfigEntry,
    coordinator: FroniusVirtualInverterCoordinator,
    serial: str,
    config: dict[str, Any],
) -> None:
    name = config.get(CONF_NAME, entry.title)
    port = int(config.get(CONF_PORT, DEFAULT_PORT))
    system_name = config.get(CONF_SYSTEM_NAME) or name

    server = FroniusSolarAPIServer(coordinator, port, serial, system_name)
    try:
        await server.start()
    except OSError as err:
        raise ConfigEntryNotReady(f"Failed to start HTTP server on port {port}: {err}") from err
    entry.async_on_unload(server.stop)

    # _http._tcp.local. via HA's zeroconf
    mdns = FroniusMDNSAnnouncer(name=name, port=port, system_name=system_name)
    try:
        await mdns.async_start(hass)
        entry.async_on_unload(mdns.async_stop)
    except Exception as err:
        _LOGGER.warning("mDNS announcement failed (non-fatal): %s", err)

    # _Fronius-SE-*._tcp.local. via raw multicast — what the Wattpilot scans for
    raw_mdns = RawMDNSAnnouncer(name=name, port=port, serial=serial, system_name=system_name)
    try:
        await raw_mdns.async_start()
        entry.async_on_unload(raw_mdns.async_stop)
    except Exception as err:
        _LOGGER.warning("Raw mDNS announcement failed (non-fatal): %s", err)

    if config.get(CONF_MODBUS_ENABLED):
        try:
            await _async_start_meter(hass, entry, coordinator, serial, config)
        except (OSError, ValueError) as err:
            # Non-fatal: the Wattpilot side still works
            _LOGGER.error("Smart Meter IP (Modbus) not started: %s", err)

    _LOGGER.info("Virtual inverter '%s' running on HTTP port %d, serial %s", name, port, serial)


async def _async_start_meter(
    hass: HomeAssistant,
    entry: FroniusConfigEntry,
    coordinator: FroniusVirtualInverterCoordinator,
    serial: str,
    config: dict[str, Any],
) -> None:
    port = int(config.get(CONF_MODBUS_PORT, DEFAULT_MODBUS_PORT))
    unit_id = int(config.get(CONF_MODBUS_ADDRESS, DEFAULT_MODBUS_ADDRESS))
    await async_add_meter(hass, port, SunSpecMeter(coordinator, serial, unit_id))
    entry.async_on_unload(partial(async_remove_meter, hass, port, unit_id))


async def async_unload_entry(hass: HomeAssistant, entry: FroniusConfigEntry) -> bool:
    """Unload a config entry. Servers are stopped by the on_unload callbacks."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Delete stored energy counters when the entry is deleted."""
    await async_remove_energy_store(hass, entry.entry_id)


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Options changed — reload to apply."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Migrate old config entries."""
    if entry.version > 1:
        return False  # downgraded from a future version

    if entry.minor_version < 2:
        # 1.1: everything lived in data/options mixed, with explicit dual-mode flags.
        # 1.2: data holds identity only (entry type, name); all settings are options.
        config = {**entry.data, **entry.options}
        for prefix, pos_key, neg_key in (
            ("p_grid", CONF_P_GRID_IMPORT_SENSOR, CONF_P_GRID_EXPORT_SENSOR),
            ("p_akku", CONF_P_AKKU_CHARGE_SENSOR, CONF_P_AKKU_DISCHARGE_SENSOR),
        ):
            pos = config.pop(f"{prefix}_sensor_pos", None)
            neg = config.pop(f"{prefix}_sensor_neg", None)
            if config.pop(f"{prefix}_dual_mode", False):
                config.pop(f"{prefix}_sensor", None)
                config[pos_key] = pos
                config[neg_key] = neg
        # 1.1 documented battery power as "+ = charging", but Fronius P_Akku is
        # "+ = discharging". Split charge/discharge sensors are now combined the
        # right way round; flip single-sensor setups to keep their meaning.
        if config.get(CONF_P_AKKU_SENSOR):
            config[CONF_P_AKKU_INVERT] = not config.get(CONF_P_AKKU_INVERT, False)

        name = config.pop(CONF_NAME, entry.title)
        config.pop(CONF_ENTRY_TYPE, None)
        hass.config_entries.async_update_entry(
            entry,
            data={CONF_ENTRY_TYPE: ENTRY_TYPE_INVERTER, CONF_NAME: name},
            options={k: v for k, v in config.items() if v not in (None, "")},
            minor_version=2,
        )
        _LOGGER.info("Migrated '%s' to config version 1.2", entry.title)

    return True
