"""Fronius Virtual Inverter — Home Assistant custom integration.

Provides two complementary emulation modes so a Fronius Wattpilot EV charger
can perform PV surplus (Eco) charging without real Fronius hardware:

  1. HTTP Solar API v1 server — impersonates a Fronius GEN24 hybrid inverter.
     The Wattpilot discovers it via mDNS and pairs with it directly.

  2. Modbus TCP Smart Meter IP server — emulates a Fronius Smart Meter IP
     (SunSpec model 213) on port 502.  A real or virtual Fronius inverter
     (or the Wattpilot itself) can use this as its primary grid meter,
     enabling surplus charging via standard Fronius meter protocols.

Both modes read the same HA sensor mappings via the shared coordinator.
"""
from __future__ import annotations

import hashlib
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_NAME, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from .const import (
    CONF_MODBUS_ENABLED,
    CONF_MODBUS_PORT,
    CONF_PORT,
    CONF_SYSTEM_NAME,
    CONF_UPDATE_INTERVAL,
    DEFAULT_MODBUS_PORT,
    DEFAULT_PORT,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
)
from .coordinator import FroniusVirtualInverterCoordinator
from .http_server import FroniusSolarAPIServer
from .mdns_announcer import FroniusMDNSAnnouncer, RawMDNSAnnouncer
from .modbus_server import FroniusSmartMeterModbusServer

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR]


def _make_serial(entry_id: str) -> str:
    """Generate a stable 8-character serial number from the entry ID."""
    return hashlib.md5(entry_id.encode()).hexdigest()[:8].upper()


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Fronius Virtual Inverter from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    # Merge data + options (options override data for reconfigured values)
    config = {**entry.data, **entry.options}

    name = config.get(CONF_NAME, entry.title)
    port = int(config.get(CONF_PORT, DEFAULT_PORT))
    serial = _make_serial(entry.entry_id)
    system_name = config.get(CONF_SYSTEM_NAME) or name

    modbus_enabled = bool(config.get(CONF_MODBUS_ENABLED, False))
    modbus_port = int(config.get(CONF_MODBUS_PORT, DEFAULT_MODBUS_PORT))

    # ── Coordinator ────────────────────────────────────────────────────────
    coordinator = FroniusVirtualInverterCoordinator(hass, config)
    await coordinator.async_config_entry_first_refresh()

    # ── HTTP Solar API server ──────────────────────────────────────────────
    server = FroniusSolarAPIServer(
        coordinator=coordinator,
        port=port,
        serial=serial,
        inverter_name=name,
        system_name=system_name,
    )
    try:
        await server.start()
    except OSError as err:
        raise ConfigEntryNotReady(
            f"Failed to start HTTP server on port {port}: {err}"
        ) from err

    # ── mDNS announcer (_http._tcp.local. via zeroconf) ───────────────────
    mdns = FroniusMDNSAnnouncer(name=name, port=port, system_name=system_name)
    try:
        await mdns.async_start(hass)
    except Exception as err:
        _LOGGER.warning("mDNS announcement failed (non-fatal): %s", err)
        mdns = None

    # ── Raw mDNS announcer (Fronius-SE service types via UDP multicast) ────
    raw_mdns = RawMDNSAnnouncer(name=name, port=port, serial=serial, system_name=system_name)
    try:
        await raw_mdns.async_start()
    except Exception as err:
        _LOGGER.warning("Raw mDNS announcement failed (non-fatal): %s", err)
        raw_mdns = None

    # ── Modbus TCP Smart Meter IP server (optional) ────────────────────────
    modbus_server: FroniusSmartMeterModbusServer | None = None
    if modbus_enabled:
        modbus_server = FroniusSmartMeterModbusServer(
            coordinator=coordinator,
            port=modbus_port,
            serial=serial,
        )
        try:
            await modbus_server.start()
            _LOGGER.info(
                "Fronius Smart Meter IP Modbus server started on port %d",
                modbus_port,
            )
        except OSError as err:
            _LOGGER.error(
                "Failed to start Modbus server on port %d: %s. "
                "Try port 5020 if 502 requires root privileges.",
                modbus_port,
                err,
            )
            modbus_server = None  # Non-fatal; HTTP server still works

    hass.data[DOMAIN][entry.entry_id] = {
        "coordinator": coordinator,
        "server": server,
        "mdns": mdns,
        "raw_mdns": raw_mdns,
        "modbus_server": modbus_server,
        "config": config,
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_options))

    _LOGGER.info(
        "Fronius Virtual Inverter '%s' running — HTTP port %d, "
        "Modbus %s (port %d), serial %s",
        name,
        port,
        "enabled" if modbus_server else "disabled",
        modbus_port,
        serial,
    )
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok and entry.entry_id in hass.data[DOMAIN]:
        data = hass.data[DOMAIN].pop(entry.entry_id)

        await data["server"].stop()

        mdns: FroniusMDNSAnnouncer | None = data.get("mdns")
        if mdns is not None:
            await mdns.async_stop()

        raw_mdns: RawMDNSAnnouncer | None = data.get("raw_mdns")
        if raw_mdns is not None:
            await raw_mdns.async_stop()

        modbus: FroniusSmartMeterModbusServer | None = data.get("modbus_server")
        if modbus is not None:
            await modbus.stop()

    return unload_ok


async def _async_update_options(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle options update — reload the entry."""
    await hass.config_entries.async_reload(entry.entry_id)
