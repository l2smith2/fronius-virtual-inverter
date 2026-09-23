"""Read numeric values from Home Assistant sensor entities."""
from __future__ import annotations

import logging

from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

# Scale to W / Wh / VA / var
_UNIT_SCALE: dict[str, float] = {
    "kW": 1e3,
    "kWh": 1e3,
    "kVA": 1e3,
    "kvar": 1e3,
    "kVAr": 1e3,
    "MW": 1e6,
    "MWh": 1e6,
}


def get_sensor_value(
    hass: HomeAssistant, entity_id: str | None, *, fraction: bool = False
) -> float | None:
    """Return a sensor's numeric state in base units, or None if unset/unavailable.

    With fraction=True a value reported in % is scaled to 0..1 (power factor).
    """
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
    if fraction and unit == "%":
        return value / 100
    return value * _UNIT_SCALE.get(unit, 1.0)


def read_signed_power(
    hass: HomeAssistant,
    sensor: str | None,
    pos_sensor: str | None = None,
    neg_sensor: str | None = None,
    invert: bool = False,
) -> float | None:
    """Read a signed power value.

    Either one signed sensor, or a split pair of positive-only sensors combined
    as pos - neg (a missing half counts as 0). The split pair wins if set.
    """
    if pos_sensor or neg_sensor:
        pos = get_sensor_value(hass, pos_sensor)
        neg = get_sensor_value(hass, neg_sensor)
        if pos is None and neg is None:
            return None
        value = (pos or 0.0) - (neg or 0.0)
    else:
        value = get_sensor_value(hass, sensor)
        if value is None:
            return None
    return -value if invert else value


def read_soc(hass: HomeAssistant, entity_id: str | None) -> float | None:
    """Read SOC value (0-100)."""
    v = get_sensor_value(hass, entity_id)
    if v is None:
        return None
    return max(0.0, min(100.0, v))
