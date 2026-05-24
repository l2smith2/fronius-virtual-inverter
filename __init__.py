"""Fronius Virtual Inverter — Home Assistant custom integration.

Impersonates a Fronius GEN24 hybrid inverter on the local network so that
a Fronius Wattpilot EV charger can pair with it and receive PV surplus data
from Home Assistant sensors — enabling solar surplus (Eco) charging without
real Fronius hardware.
"""
from __future__ import annotations

import hashlib
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_NAME, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from .const import (
    CONF_PORT,
    CONF_UPDATE_INTERVAL,
    DEFAULT_PORT,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
)
from .coordinator import FroniusVirtualInverterCoordinator
from .http_server import FroniusSolarAPIServer
from .mdns_announcer import FroniusMDNSAnnouncer

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR]


def _make_serial(entry_id: str) -> str:
    """Generate a stable 8-digit serial number from the entry ID."""
    return hashlib.md5(entry_id.encode()).hexdigest()[:8].upper()


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Fronius Virtual Inverter from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    # Merge data + options (options override data for reconfigured values)
    config = {**entry.data, **entry.options}

    name = config.get(CONF_NAME, entry.title)
    port = int(config.get(CONF_PORT, DEFAULT_PORT))
    serial = _make_serial(entry.entry_id)

    # 1. Create coordinator
    coordinator = FroniusVirtualInverterCoordinator(hass, config)

    # Do first refresh to populate data
    await coordinator.async_config_entry_first_refresh()

    # 2. Start HTTP server
    server = FroniusSolarAPIServer(
        coordinator=coordinator,
        port=port,
        serial=serial,
        inverter_name=name,
    )
    try:
        await server.start()
    except OSError as err:
        raise ConfigEntryNotReady(
            f"Failed to start HTTP server on port {port}: {err}"
        ) from err

    # 3. Start mDNS announcer
    mdns = FroniusMDNSAnnouncer(name=name, port=port)
    try:
        await mdns.start()
    except Exception as err:
        _LOGGER.warning("mDNS announcement failed (non-fatal): %s", err)
        mdns = None  # mDNS failure is non-fatal; HTTP server still works

    hass.data[DOMAIN][entry.entry_id] = {
        "coordinator": coordinator,
        "server": server,
        "mdns": mdns,
        "config": config,
    }

    # Set up sensor platform
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Listen for options updates
    entry.async_on_unload(entry.add_update_listener(_async_update_options))

    _LOGGER.info(
        "Fronius Virtual Inverter '%s' running on port %d (serial %s)",
        name, port, serial,
    )
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok and entry.entry_id in hass.data[DOMAIN]:
        data = hass.data[DOMAIN].pop(entry.entry_id)

        # Stop HTTP server
        server: FroniusSolarAPIServer = data["server"]
        await server.stop()

        # Stop mDNS
        mdns: FroniusMDNSAnnouncer | None = data.get("mdns")
        if mdns is not None:
            await mdns.stop()

    return unload_ok


async def _async_update_options(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle options update — reload the entry so config/server restarts."""
    await hass.config_entries.async_reload(entry.entry_id)
