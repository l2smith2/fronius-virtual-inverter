"""Config and options flows."""
from __future__ import annotations

from unittest.mock import patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from homeassistant.config_entries import SOURCE_USER
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.fronius_virtual_inverter.const import (
    CONF_ENTRY_TYPE,
    CONF_GRID_CT_RATING,
    CONF_GRID_PHASES,
    CONF_METER_ROLE,
    CONF_MODBUS_ADDRESS,
    CONF_MODBUS_ENABLED,
    CONF_MODBUS_PORT,
    CONF_P_AKKU_DISCHARGE_SENSOR,
    CONF_P_AKKU_INVERT,
    CONF_P_AKKU_SENSOR,
    CONF_P_GRID_IMPORT_SENSOR,
    CONF_P_GRID_INVERT,
    CONF_P_GRID_SENSOR,
    CONF_P_LOAD_INVERT,
    CONF_P_LOAD_SENSOR,
    CONF_P_PV_INVERT,
    CONF_P_PV_SENSOR,
    CONF_PORT,
    CONF_SYSTEM_NAME,
    CONF_UPDATE_INTERVAL,
    DOMAIN,
    ENTRY_TYPE_INVERTER,
    ENTRY_TYPE_METER,
    METER_ROLE_GENERATOR,
)

PKG = "custom_components.fronius_virtual_inverter"


@pytest.fixture(autouse=True)
def mock_setup_and_ports():
    """Don't actually start servers, and treat every port as free."""
    with (
        patch(f"{PKG}.async_setup_entry", return_value=True),
        patch(f"{PKG}.config_flow._port_available", return_value=True),
    ):
        yield


def _inverter_entry(hass: HomeAssistant, **options) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        version=1,
        minor_version=2,
        title="fronius-virtual",
        unique_id="fronius-virtual",
        data={CONF_ENTRY_TYPE: ENTRY_TYPE_INVERTER, CONF_NAME: "fronius-virtual"},
        options={CONF_SYSTEM_NAME: "MyHome", CONF_PORT: 80, CONF_P_GRID_SENSOR: "sensor.grid",
                 CONF_P_PV_SENSOR: "sensor.pv", **options},
    )
    entry.add_to_hass(hass)
    return entry


async def _start(hass: HomeAssistant, entry_type: str):
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    assert result["type"] is FlowResultType.MENU
    assert result["menu_options"] == ["inverter", "meter"]
    return await hass.config_entries.flow.async_configure(result["flow_id"], {"next_step_id": entry_type})


async def test_inverter_flow(hass: HomeAssistant) -> None:
    result = await _start(hass, "inverter")
    flow_id = result["flow_id"]

    result = await hass.config_entries.flow.async_configure(
        flow_id, {CONF_NAME: "my inverter", CONF_PORT: 80}
    )
    assert result["errors"] == {CONF_NAME: "invalid_hostname"}

    result = await hass.config_entries.flow.async_configure(
        flow_id, {CONF_NAME: "my-inverter", CONF_SYSTEM_NAME: "MyHome", CONF_PORT: 80}
    )
    assert result["step_id"] == "grid"

    grid = {CONF_P_PV_SENSOR: "sensor.pv", CONF_GRID_PHASES: "3", CONF_GRID_CT_RATING: 40}
    result = await hass.config_entries.flow.async_configure(flow_id, {**grid, "grid_split": {}})
    assert result["errors"] == {CONF_P_GRID_SENSOR: "sensor_required"}

    result = await hass.config_entries.flow.async_configure(
        flow_id,
        {**grid, CONF_P_GRID_SENSOR: "sensor.grid", "grid_split": {CONF_P_GRID_IMPORT_SENSOR: "sensor.imp"}},
    )
    assert result["errors"] == {"base": "sensor_conflict"}

    result = await hass.config_entries.flow.async_configure(
        flow_id, {**grid, "grid_split": {CONF_P_GRID_IMPORT_SENSOR: "sensor.imp"}}
    )
    assert result["step_id"] == "battery"

    result = await hass.config_entries.flow.async_configure(
        flow_id,
        {"battery_split": {CONF_P_AKKU_DISCHARGE_SENSOR: "sensor.dis"}},
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "my-inverter"
    assert result["data"] == {CONF_ENTRY_TYPE: ENTRY_TYPE_INVERTER, CONF_NAME: "my-inverter"}
    assert result["options"] == {
        CONF_SYSTEM_NAME: "MyHome",
        CONF_PORT: 80,
        CONF_P_PV_SENSOR: "sensor.pv",
        CONF_P_PV_INVERT: False,
        CONF_P_GRID_INVERT: False,
        CONF_P_GRID_IMPORT_SENSOR: "sensor.imp",
        CONF_GRID_PHASES: "3",
        CONF_GRID_CT_RATING: 40,
        CONF_P_AKKU_INVERT: False,
        CONF_P_LOAD_INVERT: False,
        CONF_P_AKKU_DISCHARGE_SENSOR: "sensor.dis",
    }


async def test_inverter_name_clash(hass: HomeAssistant) -> None:
    _inverter_entry(hass)
    result = await _start(hass, "inverter")
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_NAME: "other", CONF_SYSTEM_NAME: "myhome", CONF_PORT: 81}
    )
    assert result["errors"] == {CONF_SYSTEM_NAME: "name_in_use"}


async def test_meter_flow_shares_port_with_inverter_meter(hass: HomeAssistant) -> None:
    """The second meter defaults to the next free unit ID on the same port."""
    _inverter_entry(hass, **{CONF_MODBUS_ENABLED: True, CONF_MODBUS_PORT: 502, CONF_MODBUS_ADDRESS: 240})
    result = await _start(hass, "meter")
    flow_id = result["flow_id"]
    schema = {str(k): k.default() for k in result["data_schema"].schema if callable(k.default)}
    assert schema[CONF_MODBUS_ADDRESS] == 241
    assert schema[CONF_METER_ROLE] == METER_ROLE_GENERATOR

    meter = {CONF_NAME: "AC Battery", CONF_METER_ROLE: METER_ROLE_GENERATOR, CONF_MODBUS_PORT: 502}
    result = await hass.config_entries.flow.async_configure(flow_id, {**meter, CONF_MODBUS_ADDRESS: 240})
    assert result["errors"] == {CONF_MODBUS_ADDRESS: "unit_id_in_use"}

    result = await hass.config_entries.flow.async_configure(flow_id, {**meter, CONF_MODBUS_ADDRESS: 241})
    assert result["step_id"] == "meter_power"
    assert result["description_placeholders"]["positive"].startswith("producing")

    result = await hass.config_entries.flow.async_configure(
        flow_id, {CONF_P_GRID_SENSOR: "sensor.battery", CONF_GRID_PHASES: "1", "meter_split": {}}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == {CONF_ENTRY_TYPE: ENTRY_TYPE_METER, CONF_NAME: "AC Battery"}
    assert result["options"] == {
        CONF_METER_ROLE: METER_ROLE_GENERATOR,
        CONF_MODBUS_PORT: 502,
        CONF_MODBUS_ADDRESS: 241,
        CONF_P_GRID_SENSOR: "sensor.battery",
        CONF_P_GRID_INVERT: False,
        CONF_GRID_PHASES: "1",
    }


async def test_meter_port_in_use_by_other_program(hass: HomeAssistant) -> None:
    result = await _start(hass, "meter")
    with patch(f"{PKG}.config_flow._port_available", return_value=False):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_NAME: "m", CONF_METER_ROLE: "load", CONF_MODBUS_PORT: 502, CONF_MODBUS_ADDRESS: 240},
        )
    assert result["errors"] == {CONF_MODBUS_PORT: "port_in_use"}


async def test_options_menu_edits_one_section_and_clears_sensor(hass: HomeAssistant) -> None:
    entry = _inverter_entry(
        hass, **{CONF_P_LOAD_SENSOR: "sensor.load", CONF_P_LOAD_INVERT: True, CONF_P_AKKU_SENSOR: "sensor.bat"}
    )
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.MENU
    assert result["menu_options"] == ["general", "grid", "battery", "load_balancing", "modbus"]

    result = await hass.config_entries.options.async_configure(result["flow_id"], {"next_step_id": "battery"})
    # Clearing a field removes it (in 1.1 a sensor set during setup could never be removed)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {CONF_P_AKKU_SENSOR: "sensor.bat", CONF_P_AKKU_INVERT: True, CONF_P_LOAD_INVERT: True, "battery_split": {}},
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert CONF_P_LOAD_SENSOR not in entry.options
    assert entry.options[CONF_P_AKKU_INVERT] is True
    # Other sections untouched
    assert entry.options[CONF_P_GRID_SENSOR] == "sensor.grid"
    assert entry.options[CONF_SYSTEM_NAME] == "MyHome"


async def test_options_general_and_modbus(hass: HomeAssistant) -> None:
    entry = _inverter_entry(hass)
    other = MockConfigEntry(
        domain=DOMAIN, version=1, minor_version=2, title="bat",
        data={CONF_ENTRY_TYPE: ENTRY_TYPE_METER, CONF_NAME: "bat"},
        options={CONF_MODBUS_PORT: 502, CONF_MODBUS_ADDRESS: 241},
    )
    other.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(result["flow_id"], {"next_step_id": "modbus"})
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_MODBUS_ENABLED: True, CONF_MODBUS_PORT: 502, CONF_MODBUS_ADDRESS: 241}
    )
    assert result["errors"] == {CONF_MODBUS_ADDRESS: "unit_id_in_use"}
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_MODBUS_ENABLED: True, CONF_MODBUS_PORT: 502, CONF_MODBUS_ADDRESS: 240}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options[CONF_MODBUS_ADDRESS] == 240

    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(result["flow_id"], {"next_step_id": "general"})
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_PORT: 8080, CONF_UPDATE_INTERVAL: 5}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options[CONF_PORT] == 8080
    assert entry.options[CONF_UPDATE_INTERVAL] == 5
    assert CONF_SYSTEM_NAME not in entry.options  # cleared → falls back to the hostname


async def test_options_load_balancing_follows_phase_count(hass: HomeAssistant) -> None:
    entry = _inverter_entry(hass, **{CONF_GRID_PHASES: "3"})
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "load_balancing"}
    )
    assert [str(k) for k in result["data_schema"].schema] == ["phase_a", "phase_b", "phase_c"]
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {"phase_a": {"i_grid_phase_a": "sensor.ia"}, "phase_b": {}, "phase_c": {"power_factor_phase_c": "sensor.pfc"}},
    )
    assert entry.options["i_grid_phase_a"] == "sensor.ia"
    assert entry.options["power_factor_phase_c"] == "sensor.pfc"


async def test_meter_options_menu(hass: HomeAssistant) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN, version=1, minor_version=2, title="bat",
        data={CONF_ENTRY_TYPE: ENTRY_TYPE_METER, CONF_NAME: "bat"},
        options={CONF_METER_ROLE: "generator", CONF_MODBUS_PORT: 502, CONF_MODBUS_ADDRESS: 241,
                 CONF_P_GRID_SENSOR: "sensor.battery"},
    )
    entry.add_to_hass(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["menu_options"] == ["meter", "meter_power"]
    result = await hass.config_entries.options.async_configure(result["flow_id"], {"next_step_id": "meter_power"})
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {CONF_P_GRID_INVERT: True, CONF_GRID_PHASES: "1", "meter_split": {CONF_P_GRID_IMPORT_SENSOR: "sensor.charge"}},
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert CONF_P_GRID_SENSOR not in entry.options
    assert entry.options[CONF_P_GRID_IMPORT_SENSOR] == "sensor.charge"
    assert entry.options[CONF_MODBUS_ADDRESS] == 241


def test_every_form_field_has_a_label() -> None:
    """Each field (including inside sections) and menu option has English text."""
    import json
    from functools import partial
    from pathlib import Path

    from homeassistant.data_entry_flow import section

    from custom_components.fronius_virtual_inverter import config_flow as cf

    strings = json.loads(
        (Path(cf.__file__).parent / "translations" / "en.json").read_text(encoding="utf-8")
    )
    values = {CONF_GRID_PHASES: "3"}
    forms = {
        "config": {
            "inverter": partial(cf._inverter_schema, setup=True),
            "grid": cf._grid_schema,
            "battery": cf._battery_schema,
            "meter": partial(cf._meter_schema, setup=True),
            "meter_power": cf._meter_power_schema,
        },
        "options": {
            "general": partial(cf._inverter_schema, setup=False),
            "grid": cf._grid_schema,
            "battery": cf._battery_schema,
            "load_balancing": cf._load_balancing_schema,
            "modbus": cf._modbus_schema,
            "meter": partial(cf._meter_schema, setup=False),
            "meter_power": cf._meter_power_schema,
        },
    }
    assert set(strings["config"]["step"]["user"]["menu_options"]) == {"inverter", "meter"}
    assert set(strings["options"]["step"]["init"]["menu_options"]) == set(forms["options"])
    for flow, steps in forms.items():
        for step, schema_fn in steps.items():
            text = strings[flow]["step"][step]
            for marker, value in schema_fn(values).schema.items():
                if isinstance(value, section):
                    sec = text["sections"][marker.schema]
                    assert sec["name"]
                    for inner in value.schema.schema:
                        assert inner.schema in sec["data"], (flow, step, inner.schema)
                else:
                    assert marker.schema in text["data"], (flow, step, marker.schema)


@pytest.mark.parametrize(("entry_type", "error"), [("inverter", "invalid_hostname"), ("meter", "name_required")])
async def test_blank_name(hass: HomeAssistant, entry_type: str, error: str) -> None:
    result = await _start(hass, entry_type)
    fields = {CONF_PORT: 80} if entry_type == "inverter" else {
        CONF_METER_ROLE: "load", CONF_MODBUS_PORT: 502, CONF_MODBUS_ADDRESS: 240
    }
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_NAME: "   ", **fields})
    assert result["errors"] == {CONF_NAME: error}
