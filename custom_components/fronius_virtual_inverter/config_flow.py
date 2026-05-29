"""Config flow for Fronius Virtual Inverter."""
from __future__ import annotations

import logging
import socket
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.components.sensor import DOMAIN as SENSOR_DOMAIN
from homeassistant.const import CONF_NAME
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
    CONF_GRID_CT_RATING,
    CONF_GRID_PHASES,
    CONF_I_GRID_PHASE_A,
    CONF_I_GRID_PHASE_B,
    CONF_I_GRID_PHASE_C,
    CONF_MODBUS_ADDRESS,
    CONF_MODBUS_ENABLED,
    CONF_MODBUS_PORT,
    CONF_P_AKKU_DUAL_MODE,
    CONF_P_AKKU_INVERT,
    CONF_P_AKKU_SENSOR,
    CONF_P_AKKU_SENSOR_NEG,
    CONF_P_AKKU_SENSOR_POS,
    CONF_P_GRID_DUAL_MODE,
    CONF_P_GRID_INVERT,
    CONF_P_GRID_PHASE_A,
    CONF_P_GRID_PHASE_B,
    CONF_P_GRID_PHASE_C,
    CONF_P_GRID_SENSOR,
    CONF_P_GRID_SENSOR_NEG,
    CONF_P_GRID_SENSOR_POS,
    CONF_P_LOAD_INVERT,
    CONF_P_LOAD_SENSOR,
    CONF_P_PV_INVERT,
    CONF_P_PV_SENSOR,
    CONF_PORT,
    CONF_POWER_FACTOR_PHASE_A,
    CONF_POWER_FACTOR_PHASE_B,
    CONF_POWER_FACTOR_PHASE_C,
    CONF_Q_GRID_PHASE_A,
    CONF_Q_GRID_PHASE_B,
    CONF_Q_GRID_PHASE_C,
    CONF_SOC_SENSOR,
    CONF_SYSTEM_NAME,
    CONF_UPDATE_INTERVAL,
    CONF_V_GRID_PHASE_A,
    CONF_V_GRID_PHASE_B,
    CONF_V_GRID_PHASE_C,
    DEFAULT_GRID_CT_RATING,
    DEFAULT_MODBUS_ADDRESS,
    DEFAULT_MODBUS_PORT,
    DEFAULT_NAME,
    DEFAULT_PORT,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

_PER_PHASE_KEYS: tuple[str, ...] = (
    CONF_P_GRID_PHASE_A, CONF_P_GRID_PHASE_B, CONF_P_GRID_PHASE_C,
    CONF_I_GRID_PHASE_A, CONF_I_GRID_PHASE_B, CONF_I_GRID_PHASE_C,
    CONF_V_GRID_PHASE_A, CONF_V_GRID_PHASE_B, CONF_V_GRID_PHASE_C,
    CONF_POWER_FACTOR_PHASE_A, CONF_POWER_FACTOR_PHASE_B, CONF_POWER_FACTOR_PHASE_C,
    CONF_Q_GRID_PHASE_A, CONF_Q_GRID_PHASE_B, CONF_Q_GRID_PHASE_C,
)

# Keys that only apply to 3-phase — cleared when switching back to single-phase
_THREE_PHASE_KEYS: tuple[str, ...] = (
    CONF_P_GRID_PHASE_B, CONF_P_GRID_PHASE_C,
    CONF_I_GRID_PHASE_B, CONF_I_GRID_PHASE_C,
    CONF_V_GRID_PHASE_B, CONF_V_GRID_PHASE_C,
    CONF_POWER_FACTOR_PHASE_B, CONF_POWER_FACTOR_PHASE_C,
    CONF_Q_GRID_PHASE_B, CONF_Q_GRID_PHASE_C,
)

_ES = selector.EntitySelectorConfig(domain=SENSOR_DOMAIN)


def _port_available(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(("", int(port)))
            return True
        except OSError:
            return False


def _has_per_phase(config: dict) -> bool:
    return any(config.get(k) for k in _PER_PHASE_KEYS)


def _opt(key: str, current: dict) -> vol.Optional:
    """vol.Optional with suggested_value when a current value exists."""
    val = current.get(key)
    if val:
        return vol.Optional(key, description={"suggested_value": val})
    return vol.Optional(key)


def _grid_schema(current: dict) -> vol.Schema:
    return vol.Schema({
        vol.Optional(CONF_P_GRID_DUAL_MODE, default=current.get(CONF_P_GRID_DUAL_MODE, False)): selector.BooleanSelector(),
        _opt(CONF_P_GRID_SENSOR, current): selector.EntitySelector(_ES),
        _opt(CONF_P_GRID_SENSOR_POS, current): selector.EntitySelector(_ES),
        _opt(CONF_P_GRID_SENSOR_NEG, current): selector.EntitySelector(_ES),
        vol.Optional(CONF_P_GRID_INVERT, default=current.get(CONF_P_GRID_INVERT, False)): selector.BooleanSelector(),
        vol.Optional(CONF_GRID_PHASES, default=current.get(CONF_GRID_PHASES, "1")): selector.SelectSelector(
            selector.SelectSelectorConfig(options=[
                {"value": "1", "label": "Single phase (1)"},
                {"value": "3", "label": "Three phase (3)"},
            ])
        ),
        vol.Optional(CONF_GRID_CT_RATING, default=current.get(CONF_GRID_CT_RATING, DEFAULT_GRID_CT_RATING)): selector.NumberSelector(
            selector.NumberSelectorConfig(min=6, max=125, step=1, unit_of_measurement="A", mode="box")
        ),
        vol.Optional("configure_per_phase", default=_has_per_phase(current)): selector.BooleanSelector(),
    })


def _generation_schema(current: dict) -> vol.Schema:
    return vol.Schema({
        _opt(CONF_P_PV_SENSOR, current): selector.EntitySelector(_ES),
        vol.Optional(CONF_P_PV_INVERT, default=current.get(CONF_P_PV_INVERT, False)): selector.BooleanSelector(),
        vol.Optional(CONF_P_AKKU_DUAL_MODE, default=current.get(CONF_P_AKKU_DUAL_MODE, False)): selector.BooleanSelector(),
        _opt(CONF_P_AKKU_SENSOR, current): selector.EntitySelector(_ES),
        _opt(CONF_P_AKKU_SENSOR_POS, current): selector.EntitySelector(_ES),
        _opt(CONF_P_AKKU_SENSOR_NEG, current): selector.EntitySelector(_ES),
        vol.Optional(CONF_P_AKKU_INVERT, default=current.get(CONF_P_AKKU_INVERT, False)): selector.BooleanSelector(),
        _opt(CONF_P_LOAD_SENSOR, current): selector.EntitySelector(_ES),
        vol.Optional(CONF_P_LOAD_INVERT, default=current.get(CONF_P_LOAD_INVERT, False)): selector.BooleanSelector(),
        _opt(CONF_SOC_SENSOR, current): selector.EntitySelector(_ES),
    })


def _phase_a_schema(current: dict) -> vol.Schema:
    """Phase A per-phase sensors."""
    return vol.Schema({
        _opt(CONF_P_GRID_PHASE_A, current): selector.EntitySelector(_ES),
        _opt(CONF_I_GRID_PHASE_A, current): selector.EntitySelector(_ES),
        _opt(CONF_V_GRID_PHASE_A, current): selector.EntitySelector(_ES),
        _opt(CONF_POWER_FACTOR_PHASE_A, current): selector.EntitySelector(_ES),
        _opt(CONF_Q_GRID_PHASE_A, current): selector.EntitySelector(_ES),
    })


def _phase_bc_schema(current: dict) -> vol.Schema:
    """Phase B and C per-phase sensors (three-phase only)."""
    return vol.Schema({
        _opt(CONF_P_GRID_PHASE_B, current): selector.EntitySelector(_ES),
        _opt(CONF_P_GRID_PHASE_C, current): selector.EntitySelector(_ES),
        _opt(CONF_I_GRID_PHASE_B, current): selector.EntitySelector(_ES),
        _opt(CONF_I_GRID_PHASE_C, current): selector.EntitySelector(_ES),
        _opt(CONF_V_GRID_PHASE_B, current): selector.EntitySelector(_ES),
        _opt(CONF_V_GRID_PHASE_C, current): selector.EntitySelector(_ES),
        _opt(CONF_POWER_FACTOR_PHASE_B, current): selector.EntitySelector(_ES),
        _opt(CONF_POWER_FACTOR_PHASE_C, current): selector.EntitySelector(_ES),
        _opt(CONF_Q_GRID_PHASE_B, current): selector.EntitySelector(_ES),
        _opt(CONF_Q_GRID_PHASE_C, current): selector.EntitySelector(_ES),
    })


def _modbus_schema(current: dict) -> vol.Schema:
    return vol.Schema({
        vol.Optional(CONF_MODBUS_ENABLED, default=current.get(CONF_MODBUS_ENABLED, False)): selector.BooleanSelector(),
        vol.Optional(CONF_MODBUS_PORT, default=current.get(CONF_MODBUS_PORT, DEFAULT_MODBUS_PORT)): selector.NumberSelector(
            selector.NumberSelectorConfig(min=1, max=65535, mode="box")
        ),
        vol.Optional(CONF_MODBUS_ADDRESS, default=current.get(CONF_MODBUS_ADDRESS, DEFAULT_MODBUS_ADDRESS)): selector.NumberSelector(
            selector.NumberSelectorConfig(min=1, max=247, step=1, mode="box")
        ),
    })


class FroniusVirtualInverterConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Config flow for Fronius Virtual Inverter."""

    VERSION = 1

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}
        self._configure_per_phase: bool = False
        self._three_phase: bool = False

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            name = user_input[CONF_NAME]
            port = int(user_input[CONF_PORT])
            await self.async_set_unique_id(name)
            self._abort_if_unique_id_configured()
            if not await self.hass.async_add_executor_job(_port_available, port):
                errors[CONF_PORT] = "port_in_use"
            if not errors:
                self._data.update(user_input)
                return await self.async_step_grid()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required(CONF_NAME, default=DEFAULT_NAME): selector.TextSelector(),
                vol.Optional(CONF_SYSTEM_NAME): selector.TextSelector(),
                vol.Required(CONF_PORT, default=DEFAULT_PORT): selector.NumberSelector(
                    selector.NumberSelectorConfig(min=1, max=65535, mode="box")
                ),
                vol.Required(CONF_UPDATE_INTERVAL, default=DEFAULT_UPDATE_INTERVAL): selector.NumberSelector(
                    selector.NumberSelectorConfig(min=5, max=300, step=1, unit_of_measurement="s", mode="box")
                ),
            }),
            errors=errors,
        )

    async def async_step_grid(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        if user_input is not None:
            self._configure_per_phase = bool(user_input.pop("configure_per_phase", False))
            self._three_phase = user_input.get(CONF_GRID_PHASES) == "3"
            self._data.update(user_input)
            return await self.async_step_generation()
        return self.async_show_form(
            step_id="grid",
            data_schema=_grid_schema({}),
        )

    async def async_step_generation(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        if user_input is not None:
            self._data.update(user_input)
            if self._configure_per_phase:
                return await self.async_step_advanced()
            return await self.async_step_modbus()
        return self.async_show_form(
            step_id="generation",
            data_schema=_generation_schema({}),
        )

    async def async_step_advanced(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        if user_input is not None:
            self._data.update(user_input)
            if self._three_phase:
                return await self.async_step_three_phase()
            return await self.async_step_modbus()
        return self.async_show_form(
            step_id="advanced",
            data_schema=_phase_a_schema({}),
        )

    async def async_step_three_phase(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        if user_input is not None:
            self._data.update(user_input)
            return await self.async_step_modbus()
        return self.async_show_form(
            step_id="three_phase",
            data_schema=_phase_bc_schema({}),
        )

    async def async_step_modbus(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            if user_input.get(CONF_MODBUS_ENABLED):
                modbus_port = int(user_input[CONF_MODBUS_PORT])
                if not await self.hass.async_add_executor_job(_port_available, modbus_port):
                    errors[CONF_MODBUS_PORT] = "port_in_use"
            if not errors:
                self._data.update(user_input)
                return self._create_entry()
        return self.async_show_form(
            step_id="modbus",
            data_schema=_modbus_schema({}),
            errors=errors,
        )

    def _create_entry(self) -> config_entries.FlowResult:
        data = {k: v for k, v in self._data.items() if v not in ("", None)}
        return self.async_create_entry(title=data[CONF_NAME], data=data)

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        return FroniusVirtualInverterOptionsFlow(config_entry)


class FroniusVirtualInverterOptionsFlow(config_entries.OptionsFlow):
    """Options flow for Fronius Virtual Inverter."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self._config_entry = config_entry
        self._data: dict[str, Any] = {}
        self._configure_per_phase: bool = False
        self._three_phase: bool = False

    def _current(self) -> dict[str, Any]:
        return {**self._config_entry.data, **self._config_entry.options}

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        errors: dict[str, str] = {}
        current = self._current()

        if user_input is not None:
            port = int(user_input.get(CONF_PORT, current.get(CONF_PORT, DEFAULT_PORT)))
            current_port = int(current.get(CONF_PORT, DEFAULT_PORT))
            if port != current_port:
                if not await self.hass.async_add_executor_job(_port_available, port):
                    errors[CONF_PORT] = "port_in_use"
            if not errors:
                self._data.update(user_input)
                return await self.async_step_grid()

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({
                vol.Optional(CONF_PORT, default=current.get(CONF_PORT, DEFAULT_PORT)): selector.NumberSelector(
                    selector.NumberSelectorConfig(min=1, max=65535, mode="box")
                ),
                vol.Optional(CONF_UPDATE_INTERVAL, default=current.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL)): selector.NumberSelector(
                    selector.NumberSelectorConfig(min=5, max=300, step=1, unit_of_measurement="s", mode="box")
                ),
                vol.Optional(CONF_SYSTEM_NAME, description={"suggested_value": current.get(CONF_SYSTEM_NAME)}): selector.TextSelector(),
            }),
            errors=errors,
        )

    async def async_step_grid(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        current = self._current()
        if user_input is not None:
            self._configure_per_phase = bool(user_input.pop("configure_per_phase", False))
            self._three_phase = user_input.get(CONF_GRID_PHASES) == "3"
            self._data.update(user_input)
            return await self.async_step_generation()
        return self.async_show_form(
            step_id="grid",
            data_schema=_grid_schema(current),
        )

    async def async_step_generation(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        current = self._current()
        if user_input is not None:
            self._data.update(user_input)
            if self._configure_per_phase:
                return await self.async_step_advanced()
            # Per-phase skipped — preserve existing Phase A, clear B/C if now single-phase
            for key in _PER_PHASE_KEYS:
                if key in _THREE_PHASE_KEYS and not self._three_phase:
                    continue
                if current.get(key) and key not in self._data:
                    self._data[key] = current[key]
            return await self.async_step_modbus()
        return self.async_show_form(
            step_id="generation",
            data_schema=_generation_schema(current),
        )

    async def async_step_advanced(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        current = self._current()
        if user_input is not None:
            self._data.update(user_input)
            if self._three_phase:
                return await self.async_step_three_phase()
            return await self.async_step_modbus()
        return self.async_show_form(
            step_id="advanced",
            data_schema=_phase_a_schema(current),
        )

    async def async_step_three_phase(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        current = self._current()
        if user_input is not None:
            self._data.update(user_input)
            return await self.async_step_modbus()
        return self.async_show_form(
            step_id="three_phase",
            data_schema=_phase_bc_schema(current),
        )

    async def async_step_modbus(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        errors: dict[str, str] = {}
        current = self._current()
        if user_input is not None:
            modbus_enabled = bool(user_input.get(CONF_MODBUS_ENABLED, False))
            modbus_port = int(user_input.get(CONF_MODBUS_PORT, current.get(CONF_MODBUS_PORT, DEFAULT_MODBUS_PORT)))
            current_modbus_enabled = bool(current.get(CONF_MODBUS_ENABLED, False))
            current_modbus_port = int(current.get(CONF_MODBUS_PORT, DEFAULT_MODBUS_PORT))
            if modbus_enabled and (not current_modbus_enabled or modbus_port != current_modbus_port):
                if not await self.hass.async_add_executor_job(_port_available, modbus_port):
                    errors[CONF_MODBUS_PORT] = "port_in_use"
            if not errors:
                self._data.update(user_input)
                return self._save_options()
        return self.async_show_form(
            step_id="modbus",
            data_schema=_modbus_schema(current),
            errors=errors,
        )

    def _save_options(self) -> config_entries.FlowResult:
        data = {k: v for k, v in self._data.items() if v not in ("", None)}
        return self.async_create_entry(title="", data=data)
