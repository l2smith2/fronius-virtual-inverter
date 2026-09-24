"""Config flow for Fronius Virtual Inverter.

Adding the integration asks what to create — a virtual inverter (for the
Wattpilot) or a virtual smart meter (for a real Fronius inverter) — then runs a
short wizard. Afterwards "Configure" opens a menu, so any one section can be
changed without stepping through the others.

All settings are stored in entry.options; entry.data only holds the entry type
and name.
"""
from __future__ import annotations

import re
import socket
from collections.abc import Awaitable, Callable
from functools import partial
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import section
from homeassistant.helpers import selector

from .const import (
    CONF_ENTRY_TYPE,
    CONF_GRID_CT_RATING,
    CONF_GRID_PHASES,
    CONF_METER_ROLE,
    CONF_MODBUS_ADDRESS,
    CONF_MODBUS_ENABLED,
    CONF_MODBUS_PORT,
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
    CONF_PORT,
    CONF_SOC_SENSOR,
    CONF_SYSTEM_NAME,
    CONF_UPDATE_INTERVAL,
    DEFAULT_GRID_CT_RATING,
    DEFAULT_METER_NAME,
    DEFAULT_MODBUS_ADDRESS,
    DEFAULT_MODBUS_PORT,
    DEFAULT_NAME,
    DEFAULT_PORT,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
    ENTRY_TYPE_INVERTER,
    ENTRY_TYPE_METER,
    METER_ROLE_GENERATOR,
    METER_ROLE_GRID,
    METER_ROLE_LOAD,
    METER_ROLES,
    PHASE_QUANTITIES,
    PHASES,
    phase_key,
)
from .modbus_server import served_modbus_ports

# The inverter name is also its mDNS hostname (<name>.local)
_HOSTNAME = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?$")

_INT_KEYS = frozenset(
    {CONF_PORT, CONF_MODBUS_PORT, CONF_MODBUS_ADDRESS, CONF_UPDATE_INTERVAL, CONF_GRID_CT_RATING}
)

# What a positive / negative single sensor means for each meter role
_ROLE_SIGNS = {
    METER_ROLE_GENERATOR: ("producing (battery discharging)", "consuming (battery charging)"),
    METER_ROLE_LOAD: ("consuming", "feeding power back"),
    METER_ROLE_GRID: ("importing from the grid", "exporting to the grid"),
}


def _number(minimum: int, maximum: int, unit: str | None = None) -> selector.NumberSelector:
    config = selector.NumberSelectorConfig(
        min=minimum, max=maximum, step=1, mode=selector.NumberSelectorMode.BOX
    )
    if unit:
        config["unit_of_measurement"] = unit
    return selector.NumberSelector(config)


_SENSOR = selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor"))
_BOOL = selector.BooleanSelector()
_TEXT = selector.TextSelector()
_PORT = _number(1, 65535)
_UNIT_ID = _number(1, 247)
_INTERVAL = _number(1, 300, "s")
_CT_RATING = _number(6, 125, "A")
_PHASE_COUNT = selector.SelectSelector(
    selector.SelectSelectorConfig(options=["1", "3"], translation_key="grid_phases")
)
_ROLE = selector.SelectSelector(
    selector.SelectSelectorConfig(options=list(METER_ROLES), translation_key="meter_role")
)


# ── Schemas ───────────────────────────────────────────────────────────────────
# Each takes the current values (flat dict). Optional entity/text fields use a
# suggested value rather than a default so they can be cleared.

def _suggest(key: str, values: dict[str, Any], required: bool = False) -> vol.Marker:
    marker = vol.Required if required else vol.Optional
    if values.get(key):
        return marker(key, description={"suggested_value": values[key]})
    return marker(key)


def _default(key: str, values: dict[str, Any], fallback: Any) -> vol.Required:
    return vol.Required(key, default=values.get(key, fallback))


def _split_section(values: dict[str, Any], *keys: str) -> section:
    return section(
        vol.Schema({_suggest(key, values): _SENSOR for key in keys}),
        {"collapsed": not any(values.get(key) for key in keys)},
    )


def _inverter_schema(values: dict[str, Any], *, setup: bool) -> vol.Schema:
    fields: dict[Any, Any] = {}
    if setup:
        fields[_default(CONF_NAME, values, DEFAULT_NAME)] = _TEXT
    fields[_suggest(CONF_SYSTEM_NAME, values)] = _TEXT
    fields[_default(CONF_PORT, values, DEFAULT_PORT)] = _PORT
    if not setup:
        fields[_default(CONF_UPDATE_INTERVAL, values, DEFAULT_UPDATE_INTERVAL)] = _INTERVAL
    return vol.Schema(fields)


def _grid_schema(values: dict[str, Any]) -> vol.Schema:
    return vol.Schema({
        _suggest(CONF_P_GRID_SENSOR, values): _SENSOR,
        _default(CONF_P_GRID_INVERT, values, False): _BOOL,
        _suggest(CONF_P_PV_SENSOR, values, required=True): _SENSOR,
        _default(CONF_P_PV_INVERT, values, False): _BOOL,
        _default(CONF_GRID_PHASES, values, "1"): _PHASE_COUNT,
        _default(CONF_GRID_CT_RATING, values, DEFAULT_GRID_CT_RATING): _CT_RATING,
        vol.Required("grid_split"): _split_section(
            values, CONF_P_GRID_IMPORT_SENSOR, CONF_P_GRID_EXPORT_SENSOR
        ),
    })


def _battery_schema(values: dict[str, Any]) -> vol.Schema:
    return vol.Schema({
        _suggest(CONF_P_AKKU_SENSOR, values): _SENSOR,
        _default(CONF_P_AKKU_INVERT, values, False): _BOOL,
        _suggest(CONF_SOC_SENSOR, values): _SENSOR,
        _suggest(CONF_P_LOAD_SENSOR, values): _SENSOR,
        _default(CONF_P_LOAD_INVERT, values, False): _BOOL,
        vol.Required("battery_split"): _split_section(
            values, CONF_P_AKKU_CHARGE_SENSOR, CONF_P_AKKU_DISCHARGE_SENSOR
        ),
    })


def _load_balancing_schema(values: dict[str, Any]) -> vol.Schema:
    phases = PHASES if values.get(CONF_GRID_PHASES) == "3" else PHASES[:1]
    return vol.Schema({
        vol.Required(f"phase_{phase}"): section(
            vol.Schema({
                _suggest(phase_key(prefix, phase), values): _SENSOR for prefix in PHASE_QUANTITIES
            })
        )
        for phase in phases
    })


def _modbus_schema(values: dict[str, Any]) -> vol.Schema:
    return vol.Schema({
        _default(CONF_MODBUS_ENABLED, values, False): _BOOL,
        _default(CONF_MODBUS_PORT, values, DEFAULT_MODBUS_PORT): _PORT,
        _default(CONF_MODBUS_ADDRESS, values, DEFAULT_MODBUS_ADDRESS): _UNIT_ID,
    })


def _meter_schema(values: dict[str, Any], *, setup: bool) -> vol.Schema:
    fields: dict[Any, Any] = {}
    if setup:
        fields[_default(CONF_NAME, values, DEFAULT_METER_NAME)] = _TEXT
    fields[_default(CONF_METER_ROLE, values, METER_ROLE_GENERATOR)] = _ROLE
    fields[_default(CONF_MODBUS_PORT, values, DEFAULT_MODBUS_PORT)] = _PORT
    fields[_default(CONF_MODBUS_ADDRESS, values, DEFAULT_MODBUS_ADDRESS)] = _UNIT_ID
    if not setup:
        fields[_default(CONF_UPDATE_INTERVAL, values, DEFAULT_UPDATE_INTERVAL)] = _INTERVAL
    return vol.Schema(fields)


def _meter_power_schema(values: dict[str, Any]) -> vol.Schema:
    return vol.Schema({
        _suggest(CONF_P_GRID_SENSOR, values): _SENSOR,
        _default(CONF_P_GRID_INVERT, values, False): _BOOL,
        _default(CONF_GRID_PHASES, values, "1"): _PHASE_COUNT,
        vol.Required("meter_split"): _split_section(
            values, CONF_P_GRID_IMPORT_SENSOR, CONF_P_GRID_EXPORT_SENSOR
        ),
    })


# ── Helpers ───────────────────────────────────────────────────────────────────

def _schema_keys(schema: vol.Schema) -> set[str]:
    keys: set[str] = set()
    for marker, value in schema.schema.items():
        if isinstance(value, section):
            keys |= _schema_keys(value.schema)
        else:
            keys.add(marker.schema)
    return keys


def _merge(values: dict[str, Any], schema: vol.Schema, user_input: dict[str, Any]) -> dict[str, Any]:
    """Apply a submitted form: its fields replace the old ones, blank fields are removed."""
    flat: dict[str, Any] = {}
    for key, value in user_input.items():
        if isinstance(value, dict):  # a section
            flat.update(value)
        else:
            flat[key] = value
    keys = _schema_keys(schema)
    merged = {k: v for k, v in values.items() if k not in keys}
    for key, value in flat.items():
        if isinstance(value, str):
            value = value.strip()
        if value in (None, ""):
            continue
        merged[key] = int(value) if key in _INT_KEYS else value
    return merged


def _power_sensor_errors(
    values: dict[str, Any], single: str, split: tuple[str, str], required: bool
) -> dict[str, str]:
    has_split = any(values.get(key) for key in split)
    if values.get(single) and has_split:
        return {"base": "sensor_conflict"}
    if required and not values.get(single) and not has_split:
        return {single: "sensor_required"}
    return {}


def _port_available(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        try:
            sock.bind(("", port))
        except OSError:
            return False
        return True


def _entry_config(entry: ConfigEntry) -> dict[str, Any]:
    return {**entry.data, **entry.options}


def _modbus_endpoints(hass: HomeAssistant, exclude: str | None) -> set[tuple[int, int]]:
    """(port, unit ID) pairs used by other entries of this integration."""
    endpoints = set()
    for entry in hass.config_entries.async_entries(DOMAIN):
        cfg = _entry_config(entry)
        if entry.entry_id != exclude and (
            cfg.get(CONF_ENTRY_TYPE) == ENTRY_TYPE_METER or cfg.get(CONF_MODBUS_ENABLED)
        ):
            endpoints.add((
                int(cfg.get(CONF_MODBUS_PORT, DEFAULT_MODBUS_PORT)),
                int(cfg.get(CONF_MODBUS_ADDRESS, DEFAULT_MODBUS_ADDRESS)),
            ))
    return endpoints


def _names_in_use(hass: HomeAssistant, exclude: str | None) -> set[str]:
    """Names and serials (display names) of other entries, case-folded."""
    names = set()
    for entry in hass.config_entries.async_entries(DOMAIN):
        if entry.entry_id != exclude:
            cfg = _entry_config(entry)
            names |= {str(n).casefold() for n in (cfg.get(CONF_NAME), cfg.get(CONF_SYSTEM_NAME)) if n}
    return names


class _FlowMixin:
    """Form handling shared by the config and options flows."""

    hass: HomeAssistant
    _values: dict[str, Any]
    async_show_form: Callable[..., ConfigFlowResult]

    @property
    def _entry_id(self) -> str | None:
        return None

    async def _form(
        self,
        step_id: str,
        schema_fn: Callable[[dict[str, Any]], vol.Schema],
        user_input: dict[str, Any] | None,
        done: Callable[[], Awaitable[ConfigFlowResult]],
        validate: Callable[[dict[str, Any]], Awaitable[dict[str, str]]] | None = None,
        placeholders: dict[str, str] | None = None,
    ) -> ConfigFlowResult:
        """Show a form; on submit merge it into self._values, validate, then call done()."""
        values = self._values
        errors: dict[str, str] = {}
        if user_input is not None:
            values = _merge(self._values, schema_fn(self._values), user_input)
            errors = await validate(values) if validate else {}
            if not errors:
                self._values = values
                return await done()
        return self.async_show_form(
            step_id=step_id,
            data_schema=schema_fn(values),
            errors=errors,
            description_placeholders=placeholders,
        )

    async def _port_errors(self, key: str, port: int, current: int | None) -> dict[str, str]:
        if port != current and not await self.hass.async_add_executor_job(_port_available, port):
            return {key: "port_in_use"}
        return {}

    async def _modbus_errors(self, values: dict[str, Any]) -> dict[str, str]:
        port = values[CONF_MODBUS_PORT]
        if (port, values[CONF_MODBUS_ADDRESS]) in _modbus_endpoints(self.hass, self._entry_id):
            return {CONF_MODBUS_ADDRESS: "unit_id_in_use"}
        if port in served_modbus_ports(self.hass):
            return {}  # our own shared server — more meters can join it
        return await self._port_errors(CONF_MODBUS_PORT, port, None)

    def _name_errors(self, key: str, name: str | None) -> dict[str, str]:
        if name and name.casefold() in _names_in_use(self.hass, self._entry_id):
            return {key: "name_in_use"}
        return {}

    async def _validate_grid(self, values: dict[str, Any]) -> dict[str, str]:
        """Grid power (inverter) or metered power (meter): one signed sensor or a split pair."""
        return _power_sensor_errors(
            values, CONF_P_GRID_SENSOR, (CONF_P_GRID_IMPORT_SENSOR, CONF_P_GRID_EXPORT_SENSOR), True
        )

    async def _validate_battery(self, values: dict[str, Any]) -> dict[str, str]:
        return _power_sensor_errors(
            values, CONF_P_AKKU_SENSOR, (CONF_P_AKKU_CHARGE_SENSOR, CONF_P_AKKU_DISCHARGE_SENSOR), False
        )

    async def _validate_modbus(self, values: dict[str, Any]) -> dict[str, str]:
        return await self._modbus_errors(values) if values.get(CONF_MODBUS_ENABLED) else {}

    def _meter_power_placeholders(self) -> dict[str, str]:
        positive, negative = _ROLE_SIGNS[self._values.get(CONF_METER_ROLE, METER_ROLE_GENERATOR)]
        return {"positive": positive, "negative": negative}


class FroniusVirtualInverterConfigFlow(_FlowMixin, ConfigFlow, domain=DOMAIN):
    """Add a virtual inverter or virtual smart meter."""

    VERSION = 1
    MINOR_VERSION = 2

    def __init__(self) -> None:
        self._values = {}

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return FroniusVirtualInverterOptionsFlow()

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        return self.async_show_menu(step_id="user", menu_options=["inverter", "meter"])

    # ── Virtual inverter ─────────────────────────────────────────────────

    async def async_step_inverter(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        self._values.setdefault(CONF_ENTRY_TYPE, ENTRY_TYPE_INVERTER)
        return await self._form(
            "inverter",
            partial(_inverter_schema, setup=True),
            user_input,
            self.async_step_grid,
            self._validate_inverter,
        )

    async def _validate_inverter(self, values: dict[str, Any]) -> dict[str, str]:
        name = values.get(CONF_NAME, "")
        if not _HOSTNAME.match(name):
            return {CONF_NAME: "invalid_hostname"}
        errors = self._name_errors(CONF_NAME, name) or self._name_errors(
            CONF_SYSTEM_NAME, values.get(CONF_SYSTEM_NAME)
        )
        return errors or await self._port_errors(CONF_PORT, values[CONF_PORT], None)

    async def async_step_grid(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        return await self._form("grid", _grid_schema, user_input, self.async_step_battery, self._validate_grid)

    async def async_step_battery(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        return await self._form("battery", _battery_schema, user_input, self._create, self._validate_battery)

    # ── Virtual smart meter ──────────────────────────────────────────────

    async def async_step_meter(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if CONF_ENTRY_TYPE not in self._values:
            used = {unit for port, unit in _modbus_endpoints(self.hass, None) if port == DEFAULT_MODBUS_PORT}
            self._values = {
                CONF_ENTRY_TYPE: ENTRY_TYPE_METER,
                CONF_MODBUS_ADDRESS: next(
                    (u for u in range(DEFAULT_MODBUS_ADDRESS, 248) if u not in used),
                    DEFAULT_MODBUS_ADDRESS,
                ),
            }
        return await self._form(
            "meter",
            partial(_meter_schema, setup=True),
            user_input,
            self.async_step_meter_power,
            self._validate_meter,
        )

    async def _validate_meter(self, values: dict[str, Any]) -> dict[str, str]:
        if not values.get(CONF_NAME):
            return {CONF_NAME: "name_required"}
        return self._name_errors(CONF_NAME, values[CONF_NAME]) or await self._modbus_errors(values)

    async def async_step_meter_power(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        return await self._form(
            "meter_power",
            _meter_power_schema,
            user_input,
            self._create,
            self._validate_grid,
            self._meter_power_placeholders(),
        )

    async def _create(self) -> ConfigFlowResult:
        name = self._values[CONF_NAME]
        await self.async_set_unique_id(name)
        self._abort_if_unique_id_configured()
        data = {CONF_ENTRY_TYPE: self._values[CONF_ENTRY_TYPE], CONF_NAME: name}
        options = {k: v for k, v in self._values.items() if k not in data}
        return self.async_create_entry(title=name, data=data, options=options)


class FroniusVirtualInverterOptionsFlow(_FlowMixin, OptionsFlow):
    """Edit one section at a time."""

    @property
    def _entry_id(self) -> str | None:
        return self.config_entry.entry_id

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        self._values = _entry_config(self.config_entry)
        if self._values.get(CONF_ENTRY_TYPE) == ENTRY_TYPE_METER:
            menu = ["meter", "meter_power"]
        else:
            menu = ["general", "grid", "battery", "load_balancing", "modbus"]
        return self.async_show_menu(step_id="init", menu_options=menu)

    async def _save(self) -> ConfigFlowResult:
        data = self.config_entry.data
        return self.async_create_entry(data={k: v for k, v in self._values.items() if k not in data})

    async def async_step_general(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        return await self._form(
            "general", partial(_inverter_schema, setup=False), user_input, self._save, self._validate_general
        )

    async def _validate_general(self, values: dict[str, Any]) -> dict[str, str]:
        current = int(self._values.get(CONF_PORT, DEFAULT_PORT))
        return self._name_errors(CONF_SYSTEM_NAME, values.get(CONF_SYSTEM_NAME)) or await self._port_errors(
            CONF_PORT, values[CONF_PORT], current
        )

    async def async_step_grid(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        return await self._form("grid", _grid_schema, user_input, self._save, self._validate_grid)

    async def async_step_battery(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        return await self._form("battery", _battery_schema, user_input, self._save, self._validate_battery)

    async def async_step_load_balancing(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        return await self._form("load_balancing", _load_balancing_schema, user_input, self._save)

    async def async_step_modbus(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        return await self._form("modbus", _modbus_schema, user_input, self._save, self._validate_modbus)

    async def async_step_meter(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        return await self._form(
            "meter", partial(_meter_schema, setup=False), user_input, self._save, self._modbus_errors
        )

    async def async_step_meter_power(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        return await self._form(
            "meter_power",
            _meter_power_schema,
            user_input,
            self._save,
            self._validate_grid,
            self._meter_power_placeholders(),
        )
