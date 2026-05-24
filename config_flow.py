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
    CONF_PORT,
    CONF_SOC_SENSOR,
    CONF_UPDATE_INTERVAL,
    DEFAULT_NAME,
    DEFAULT_PORT,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

# Entity selector for sensors (numeric/power sensors)
SENSOR_SELECTOR = selector.EntitySelector(
    selector.EntitySelectorConfig(domain=SENSOR_DOMAIN)
)
OPTIONAL_SENSOR_SELECTOR = selector.EntitySelector(
    selector.EntitySelectorConfig(domain=SENSOR_DOMAIN, multiple=False)
)


def _port_available(port: int) -> bool:
    """Check if a port is available."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(("", port))
            return True
        except OSError:
            return False


def _basic_schema(defaults: dict) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(CONF_NAME, default=defaults.get(CONF_NAME, DEFAULT_NAME)): str,
            vol.Required(CONF_PORT, default=defaults.get(CONF_PORT, DEFAULT_PORT)): vol.All(
                int, vol.Range(min=1024, max=65535)
            ),
            vol.Required(
                CONF_UPDATE_INTERVAL,
                default=defaults.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL),
            ): vol.All(int, vol.Range(min=5, max=300)),
        }
    )


def _sensor_schema(defaults: dict) -> vol.Schema:
    """Build the sensor mapping schema."""
    return vol.Schema(
        {
            # P_Grid
            vol.Optional(CONF_P_GRID_DUAL_MODE, default=defaults.get(CONF_P_GRID_DUAL_MODE, False)): bool,
            vol.Optional(CONF_P_GRID_SENSOR, default=defaults.get(CONF_P_GRID_SENSOR, "")): str,
            vol.Optional(CONF_P_GRID_SENSOR_POS, default=defaults.get(CONF_P_GRID_SENSOR_POS, "")): str,
            vol.Optional(CONF_P_GRID_SENSOR_NEG, default=defaults.get(CONF_P_GRID_SENSOR_NEG, "")): str,
            vol.Optional(CONF_P_GRID_INVERT, default=defaults.get(CONF_P_GRID_INVERT, False)): bool,
            # P_PV
            vol.Optional(CONF_P_PV_SENSOR, default=defaults.get(CONF_P_PV_SENSOR, "")): str,
            vol.Optional(CONF_P_PV_INVERT, default=defaults.get(CONF_P_PV_INVERT, False)): bool,
            # P_Akku
            vol.Optional(CONF_P_AKKU_DUAL_MODE, default=defaults.get(CONF_P_AKKU_DUAL_MODE, False)): bool,
            vol.Optional(CONF_P_AKKU_SENSOR, default=defaults.get(CONF_P_AKKU_SENSOR, "")): str,
            vol.Optional(CONF_P_AKKU_SENSOR_POS, default=defaults.get(CONF_P_AKKU_SENSOR_POS, "")): str,
            vol.Optional(CONF_P_AKKU_SENSOR_NEG, default=defaults.get(CONF_P_AKKU_SENSOR_NEG, "")): str,
            vol.Optional(CONF_P_AKKU_INVERT, default=defaults.get(CONF_P_AKKU_INVERT, False)): bool,
            # P_Load
            vol.Optional(CONF_P_LOAD_SENSOR, default=defaults.get(CONF_P_LOAD_SENSOR, "")): str,
            vol.Optional(CONF_P_LOAD_INVERT, default=defaults.get(CONF_P_LOAD_INVERT, False)): bool,
            # SOC
            vol.Optional(CONF_SOC_SENSOR, default=defaults.get(CONF_SOC_SENSOR, "")): str,
        }
    )


def _sensor_schema_ui(defaults: dict) -> vol.Schema:
    """Sensor schema with UI selectors."""
    return vol.Schema(
        {
            # P_Grid
            vol.Optional(CONF_P_GRID_DUAL_MODE, default=defaults.get(CONF_P_GRID_DUAL_MODE, False)): selector.BooleanSelector(),
            vol.Optional(CONF_P_GRID_SENSOR): selector.EntitySelector(
                selector.EntitySelectorConfig(domain=SENSOR_DOMAIN)
            ),
            vol.Optional(CONF_P_GRID_SENSOR_POS): selector.EntitySelector(
                selector.EntitySelectorConfig(domain=SENSOR_DOMAIN)
            ),
            vol.Optional(CONF_P_GRID_SENSOR_NEG): selector.EntitySelector(
                selector.EntitySelectorConfig(domain=SENSOR_DOMAIN)
            ),
            vol.Optional(CONF_P_GRID_INVERT, default=defaults.get(CONF_P_GRID_INVERT, False)): selector.BooleanSelector(),
            # P_PV
            vol.Optional(CONF_P_PV_SENSOR): selector.EntitySelector(
                selector.EntitySelectorConfig(domain=SENSOR_DOMAIN)
            ),
            vol.Optional(CONF_P_PV_INVERT, default=defaults.get(CONF_P_PV_INVERT, False)): selector.BooleanSelector(),
            # P_Akku
            vol.Optional(CONF_P_AKKU_DUAL_MODE, default=defaults.get(CONF_P_AKKU_DUAL_MODE, False)): selector.BooleanSelector(),
            vol.Optional(CONF_P_AKKU_SENSOR): selector.EntitySelector(
                selector.EntitySelectorConfig(domain=SENSOR_DOMAIN)
            ),
            vol.Optional(CONF_P_AKKU_SENSOR_POS): selector.EntitySelector(
                selector.EntitySelectorConfig(domain=SENSOR_DOMAIN)
            ),
            vol.Optional(CONF_P_AKKU_SENSOR_NEG): selector.EntitySelector(
                selector.EntitySelectorConfig(domain=SENSOR_DOMAIN)
            ),
            vol.Optional(CONF_P_AKKU_INVERT, default=defaults.get(CONF_P_AKKU_INVERT, False)): selector.BooleanSelector(),
            # P_Load
            vol.Optional(CONF_P_LOAD_SENSOR): selector.EntitySelector(
                selector.EntitySelectorConfig(domain=SENSOR_DOMAIN)
            ),
            vol.Optional(CONF_P_LOAD_INVERT, default=defaults.get(CONF_P_LOAD_INVERT, False)): selector.BooleanSelector(),
            # SOC
            vol.Optional(CONF_SOC_SENSOR): selector.EntitySelector(
                selector.EntitySelectorConfig(domain=SENSOR_DOMAIN)
            ),
        }
    )


class FroniusVirtualInverterConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Config flow for Fronius Virtual Inverter."""

    VERSION = 1

    def __init__(self) -> None:
        self._user_input: dict[str, Any] = {}

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            name = user_input[CONF_NAME]
            port = user_input[CONF_PORT]

            # Check for duplicate name
            await self.async_set_unique_id(name)
            self._abort_if_unique_id_configured()

            # Check port availability
            if not await self.hass.async_add_executor_job(_port_available, port):
                errors[CONF_PORT] = "port_in_use"

            if not errors:
                self._user_input = user_input
                return await self.async_step_sensors()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_NAME, default=DEFAULT_NAME): selector.TextSelector(),
                    vol.Required(CONF_PORT, default=DEFAULT_PORT): selector.NumberSelector(
                        selector.NumberSelectorConfig(min=1024, max=65535, mode="box")
                    ),
                    vol.Required(CONF_UPDATE_INTERVAL, default=DEFAULT_UPDATE_INTERVAL): selector.NumberSelector(
                        selector.NumberSelectorConfig(min=5, max=300, step=1, unit_of_measurement="s", mode="box")
                    ),
                }
            ),
            errors=errors,
        )

    async def async_step_sensors(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        if user_input is not None:
            # Merge with first step data
            data = {**self._user_input, **user_input}
            # Clean empty strings
            data = {k: v for k, v in data.items() if v != ""}
            return self.async_create_entry(
                title=self._user_input[CONF_NAME],
                data=data,
            )

        return self.async_show_form(
            step_id="sensors",
            data_schema=_sensor_schema_ui({}),
        )

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

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        errors: dict[str, str] = {}

        current = {**self._config_entry.data, **self._config_entry.options}

        if user_input is not None:
            port = int(user_input.get(CONF_PORT, current.get(CONF_PORT, DEFAULT_PORT)))
            current_port = current.get(CONF_PORT, DEFAULT_PORT)

            if port != current_port:
                if not await self.hass.async_add_executor_job(_port_available, port):
                    errors[CONF_PORT] = "port_in_use"

            if not errors:
                data = {k: v for k, v in user_input.items() if v != "" and v is not None}
                return self.async_create_entry(title="", data=data)

        schema = vol.Schema(
            {
                vol.Optional(CONF_PORT, default=current.get(CONF_PORT, DEFAULT_PORT)): selector.NumberSelector(
                    selector.NumberSelectorConfig(min=1024, max=65535, mode="box")
                ),
                vol.Optional(CONF_UPDATE_INTERVAL, default=current.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL)): selector.NumberSelector(
                    selector.NumberSelectorConfig(min=5, max=300, step=1, unit_of_measurement="s", mode="box")
                ),
                # P_Grid
                vol.Optional(CONF_P_GRID_DUAL_MODE, default=current.get(CONF_P_GRID_DUAL_MODE, False)): selector.BooleanSelector(),
                vol.Optional(CONF_P_GRID_SENSOR, description={"suggested_value": current.get(CONF_P_GRID_SENSOR)}): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain=SENSOR_DOMAIN)
                ),
                vol.Optional(CONF_P_GRID_SENSOR_POS, description={"suggested_value": current.get(CONF_P_GRID_SENSOR_POS)}): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain=SENSOR_DOMAIN)
                ),
                vol.Optional(CONF_P_GRID_SENSOR_NEG, description={"suggested_value": current.get(CONF_P_GRID_SENSOR_NEG)}): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain=SENSOR_DOMAIN)
                ),
                vol.Optional(CONF_P_GRID_INVERT, default=current.get(CONF_P_GRID_INVERT, False)): selector.BooleanSelector(),
                # P_PV
                vol.Optional(CONF_P_PV_SENSOR, description={"suggested_value": current.get(CONF_P_PV_SENSOR)}): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain=SENSOR_DOMAIN)
                ),
                vol.Optional(CONF_P_PV_INVERT, default=current.get(CONF_P_PV_INVERT, False)): selector.BooleanSelector(),
                # P_Akku
                vol.Optional(CONF_P_AKKU_DUAL_MODE, default=current.get(CONF_P_AKKU_DUAL_MODE, False)): selector.BooleanSelector(),
                vol.Optional(CONF_P_AKKU_SENSOR, description={"suggested_value": current.get(CONF_P_AKKU_SENSOR)}): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain=SENSOR_DOMAIN)
                ),
                vol.Optional(CONF_P_AKKU_SENSOR_POS, description={"suggested_value": current.get(CONF_P_AKKU_SENSOR_POS)}): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain=SENSOR_DOMAIN)
                ),
                vol.Optional(CONF_P_AKKU_SENSOR_NEG, description={"suggested_value": current.get(CONF_P_AKKU_SENSOR_NEG)}): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain=SENSOR_DOMAIN)
                ),
                vol.Optional(CONF_P_AKKU_INVERT, default=current.get(CONF_P_AKKU_INVERT, False)): selector.BooleanSelector(),
                # P_Load
                vol.Optional(CONF_P_LOAD_SENSOR, description={"suggested_value": current.get(CONF_P_LOAD_SENSOR)}): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain=SENSOR_DOMAIN)
                ),
                vol.Optional(CONF_P_LOAD_INVERT, default=current.get(CONF_P_LOAD_INVERT, False)): selector.BooleanSelector(),
                # SOC
                vol.Optional(CONF_SOC_SENSOR, description={"suggested_value": current.get(CONF_SOC_SENSOR)}): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain=SENSOR_DOMAIN)
                ),
            }
        )

        return self.async_show_form(
            step_id="init",
            data_schema=schema,
            errors=errors,
        )
