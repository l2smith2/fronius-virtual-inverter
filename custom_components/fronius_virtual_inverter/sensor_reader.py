"""Sensor value reader with dual mode and sign invert support."""
from __future__ import annotations

import logging

from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)


def _get_sensor_value(hass: HomeAssistant, entity_id: str | None) -> float | None:
    """Get the numeric state of a sensor entity, converting kW/MW/kWh/MWh to W/Wh."""
    if not entity_id:
        return None
    state = hass.states.get(entity_id)
    if state is None or state.state in ("unavailable", "unknown", ""):
        return None
    try:
        value = float(state.state)
    except (ValueError, TypeError):
        _LOGGER.warning("Cannot convert state '%s' to float for entity %s", state.state, entity_id)
        return None

    unit = state.attributes.get("unit_of_measurement", "")
    if unit in ("kW", "kWh"):
        value *= 1000
    elif unit in ("MW", "MWh"):
        value *= 1_000_000

    return value


def read_power_value(
    hass: HomeAssistant,
    single_sensor: str | None,
    pos_sensor: str | None,
    neg_sensor: str | None,
    dual_mode: bool,
    invert: bool,
) -> float | None:
    """
    Read a power value.

    In dual mode: result = pos_value - neg_value (neg sensor is absolute value of the
    negative direction, e.g. export W or discharge W, so we subtract it).

    In single mode: result = single_value (already signed).

    Then applies invert if requested.
    """
    value: float | None = None

    if dual_mode:
        pos = _get_sensor_value(hass, pos_sensor)
        neg = _get_sensor_value(hass, neg_sensor)
        if pos is not None or neg is not None:
            value = (pos or 0.0) - (neg or 0.0)
    else:
        value = _get_sensor_value(hass, single_sensor)

    if value is None:
        return None

    if invert:
        value = -value

    return value


def read_soc(hass: HomeAssistant, entity_id: str | None) -> float | None:
    """Read SOC value (0-100)."""
    v = _get_sensor_value(hass, entity_id)
    if v is None:
        return None
    return max(0.0, min(100.0, v))
