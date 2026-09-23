"""Setup, migration, unload and the running servers."""
from __future__ import annotations

import asyncio
import json
import struct
from unittest.mock import patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_fire_time_changed

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant

from custom_components.fronius_virtual_inverter import async_migrate_entry
from custom_components.fronius_virtual_inverter.const import (
    CONF_ENTRY_TYPE,
    DOMAIN,
    ENTRY_TYPE_INVERTER,
    ENTRY_TYPE_METER,
)

PKG = "custom_components.fronius_virtual_inverter"


def _v1_1_entry(http_port: int, modbus_port: int, **extra) -> MockConfigEntry:
    """An entry exactly as version 1.1.0 stored it."""
    return MockConfigEntry(
        domain=DOMAIN,
        version=1,
        minor_version=1,
        title="fronius-virtual",
        unique_id="fronius-virtual",
        data={
            "name": "fronius-virtual",
            "system_name": "MyHome",
            "port": float(http_port),
            "update_interval": 10.0,
            "p_grid_dual_mode": False,
            "p_grid_sensor": "sensor.grid",
            "p_grid_sensor_pos": "sensor.stale_left_over",
            "p_grid_invert": False,
            "p_pv_sensor": "sensor.pv",
            "p_akku_dual_mode": True,
            "p_akku_sensor_pos": "sensor.charge",
            "p_akku_sensor_neg": "sensor.discharge",
            "p_akku_invert": False,
            "grid_phases": "1",
            "grid_ct_rating": 32.0,
            "modbus_enabled": True,
            "modbus_port": float(modbus_port),
            "modbus_address": 240.0,
            **extra,
        },
        options={"p_load_sensor": "sensor.load", "p_load_invert": True},
    )


def _set_states(hass: HomeAssistant) -> None:
    hass.states.async_set("sensor.grid", "-1.5", {"unit_of_measurement": "kW"})
    hass.states.async_set("sensor.pv", "4000", {"unit_of_measurement": "W"})
    hass.states.async_set("sensor.charge", "2000", {"unit_of_measurement": "W"})
    hass.states.async_set("sensor.discharge", "0", {"unit_of_measurement": "W"})
    hass.states.async_set("sensor.load", "500", {"unit_of_measurement": "W"})
    hass.states.async_set("sensor.battery", "1200", {"unit_of_measurement": "W"})


async def _http_get(port: int, path: str) -> dict:
    reader, writer = await asyncio.open_connection("127.0.0.1", port)
    writer.write(f"GET {path} HTTP/1.1\r\nHost: x\r\nConnection: close\r\n\r\n".encode())
    raw = await asyncio.wait_for(reader.read(), 5)
    writer.close()
    return json.loads(raw.split(b"\r\n\r\n", 1)[1])


async def _modbus_float(reader, writer, unit: int, address: int) -> float:
    writer.write(struct.pack(">HHHBBHH", 1, 0, 6, unit, 3, address, 2))
    await writer.drain()
    reply = await asyncio.wait_for(reader.readexactly(13), 2)
    return struct.unpack(">f", reply[9:13])[0]


async def test_migrate_single_battery_sensor_keeps_meaning(hass: HomeAssistant) -> None:
    """1.1 documented battery power as '+ = charging'; Fronius P_Akku is '+ = discharging'."""
    entry = _v1_1_entry(80, 502, p_akku_dual_mode=False, p_akku_sensor="sensor.bat")
    entry.add_to_hass(hass)
    assert await async_migrate_entry(hass, entry)
    assert entry.options["p_akku_sensor"] == "sensor.bat"
    assert entry.options["p_akku_invert"] is True
    assert "p_akku_charge_sensor" not in entry.options


async def test_migrated_inverter_serves_and_unloads(
    hass: HomeAssistant, socket_enabled, unused_tcp_port_factory, no_mdns
) -> None:
    http_port, modbus_port = unused_tcp_port_factory(), unused_tcp_port_factory()
    _set_states(hass)
    entry = _v1_1_entry(http_port, modbus_port)
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED

    # Migrated layout
    assert entry.minor_version == 2
    assert entry.data == {CONF_ENTRY_TYPE: ENTRY_TYPE_INVERTER, "name": "fronius-virtual"}
    opts = entry.options
    assert opts["p_grid_sensor"] == "sensor.grid"
    assert opts["p_akku_charge_sensor"] == "sensor.charge"
    assert opts["p_akku_discharge_sensor"] == "sensor.discharge"
    assert opts["p_load_sensor"] == "sensor.load"
    for gone in ("p_grid_dual_mode", "p_akku_dual_mode", "p_grid_sensor_pos", "p_akku_sensor_pos", "name"):
        assert gone not in opts

    # Solar API: kW converted, P_Akku negative while charging (Fronius convention)
    flow = await _http_get(http_port, "/solar_api/v1/GetPowerFlowRealtimeData.fcgi")
    site = flow["Body"]["Data"]["Site"]
    assert site["P_Grid"] == -1500.0
    assert site["P_Akku"] == -2000.0
    assert site["P_Load"] == -500.0
    assert site["rel_Autonomy"] == 100.0
    assert site["rel_SelfConsumption"] == 62.5  # 1.5 of 4 kW exported
    meter = await _http_get(http_port, "/solar_api/v1/GetMeterRealtimeData.cgi?Scope=Device&DeviceId=0")
    assert meter["Body"]["Data"]["PowerReal_P_Sum"] == -1500.0  # Device scope: flat

    # Diagnostic sensor mirrors it
    assert hass.states.get("sensor.fronius_virtual_battery_power").state == "-2000.0"

    # Modbus grid meter, with Fronius holding its connection open
    reader, writer = await asyncio.open_connection("127.0.0.1", modbus_port)
    assert await _modbus_float(reader, writer, 240, 40097) == -1500.0

    # Regression: this unload used to hang forever (Modbus wait_closed)
    assert await asyncio.wait_for(hass.config_entries.async_unload(entry.entry_id), 10)
    assert entry.state is ConfigEntryState.NOT_LOADED
    assert await reader.read() == b""
    writer.close()


async def test_battery_meter_shares_port_with_inverter(
    hass: HomeAssistant, socket_enabled, unused_tcp_port_factory, no_mdns
) -> None:
    http_port, modbus_port = unused_tcp_port_factory(), unused_tcp_port_factory()
    _set_states(hass)
    inverter = _v1_1_entry(http_port, modbus_port)
    battery = MockConfigEntry(
        domain=DOMAIN,
        version=1,
        minor_version=2,
        title="AC Battery",
        unique_id="AC Battery",
        data={CONF_ENTRY_TYPE: ENTRY_TYPE_METER, "name": "AC Battery"},
        options={
            "meter_role": "generator",
            "modbus_port": modbus_port,
            "modbus_address": 241,
            "p_grid_sensor": "sensor.battery",  # + = discharging (producing)
        },
    )
    inverter.add_to_hass(hass)
    battery.add_to_hass(hass)
    assert await hass.config_entries.async_setup(inverter.entry_id)  # loads every entry of the domain
    await hass.async_block_till_done()
    assert battery.state is ConfigEntryState.LOADED

    reader, writer = await asyncio.open_connection("127.0.0.1", modbus_port)
    assert await _modbus_float(reader, writer, 240, 40097) == -1500.0  # grid
    # A discharging battery at an external-generator meter reads as power towards the grid
    assert await _modbus_float(reader, writer, 241, 40097) == -1200.0
    assert hass.states.get("sensor.ac_battery_meter_power").state == "-1200.0"
    assert hass.states.get("sensor.ac_battery_pv_power") is None  # inverter-only sensors not created

    # Reloading the inverter leaves the battery meter (and the connection) up
    assert await hass.config_entries.async_reload(inverter.entry_id)
    assert await _modbus_float(reader, writer, 241, 40097) == -1200.0

    assert await hass.config_entries.async_unload(battery.entry_id)
    assert await hass.config_entries.async_unload(inverter.entry_id)
    assert await reader.read() == b""
    writer.close()


async def test_energy_counters_persist(
    hass: HomeAssistant, hass_storage, socket_enabled, unused_tcp_port_factory
) -> None:
    hass.states.async_set("sensor.battery", "1000", {"unit_of_measurement": "W"})
    entry = MockConfigEntry(
        domain=DOMAIN,
        version=1,
        minor_version=2,
        title="bat",
        data={CONF_ENTRY_TYPE: ENTRY_TYPE_METER, "name": "bat"},
        options={"meter_role": "generator", "modbus_port": unused_tcp_port_factory(),
                 "modbus_address": 241, "p_grid_sensor": "sensor.battery"},
    )
    entry.add_to_hass(hass)
    clock = [1000.0]
    with patch(f"{PKG}.coordinator.monotonic", side_effect=lambda: clock[0]):
        assert await hass.config_entries.async_setup(entry.entry_id)
        coordinator = entry.runtime_data
        for _ in range(12):  # one hour discharging at 1 kW, in 5-minute updates
            clock[0] += 300
            await coordinator.async_refresh()
        clock[0] += 3600  # a stalled update never adds more than 5 minutes
        await coordinator.async_refresh()
    assert coordinator.data["_tot_wh_exp"] == pytest.approx(1000.0 + 1000 * 300 / 3600)
    assert coordinator.data["_tot_wh_imp"] == 0.0

    assert await hass.config_entries.async_unload(entry.entry_id)
    stored = hass_storage[f"{DOMAIN}.{entry.entry_id}"]["data"]["_tot_wh_exp"]
    assert stored == pytest.approx(coordinator.data["_tot_wh_exp"])

    # A restart continues from the stored total instead of 0
    assert await hass.config_entries.async_setup(entry.entry_id)
    assert entry.runtime_data.data["_tot_wh_exp"] == pytest.approx(stored)
    assert await hass.config_entries.async_unload(entry.entry_id)

    await hass.config_entries.async_remove(entry.entry_id)
    await hass.async_block_till_done()
    assert f"{DOMAIN}.{entry.entry_id}" not in hass_storage


async def test_day_counter_resets(hass: HomeAssistant, hass_storage, socket_enabled, unused_tcp_port_factory, no_mdns) -> None:
    hass.states.async_set("sensor.grid", "0")
    hass.states.async_set("sensor.pv", "0")
    hass_storage["fronius_virtual_inverter.entry1"] = {
        "version": 1,
        "key": "fronius_virtual_inverter.entry1",
        "data": {"E_Day": 5000.0, "E_Year": 9000.0, "E_Total": 12000.0, "day": "2000-01-01", "year": 2000},
    }
    entry = MockConfigEntry(
        domain=DOMAIN, version=1, minor_version=2, title="inv", entry_id="entry1",
        data={CONF_ENTRY_TYPE: ENTRY_TYPE_INVERTER, "name": "inv"},
        options={"port": unused_tcp_port_factory(), "p_grid_sensor": "sensor.grid", "p_pv_sensor": "sensor.pv"},
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    data = entry.runtime_data.data
    assert data["E_Day"] == 0.0 and data["E_Year"] == 0.0
    assert data["E_Total"] == 12000.0
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_energy_saved_periodically_while_running(
    hass: HomeAssistant, hass_storage, freezer, socket_enabled, unused_tcp_port_factory
) -> None:
    """Counters reach disk while updates keep coming, not only on unload/shutdown."""
    hass.states.async_set("sensor.battery", "1000")
    entry = MockConfigEntry(
        domain=DOMAIN, version=1, minor_version=2, title="bat",
        data={CONF_ENTRY_TYPE: ENTRY_TYPE_METER, "name": "bat"},
        options={"meter_role": "generator", "modbus_port": unused_tcp_port_factory(),
                 "modbus_address": 241, "p_grid_sensor": "sensor.battery", "update_interval": 10},
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    key = f"{DOMAIN}.{entry.entry_id}"
    for _ in range(40):  # 400 s of 10 s updates
        freezer.tick(10)
        async_fire_time_changed(hass)
        await hass.async_block_till_done()
    assert key in hass_storage
    assert hass_storage[key]["data"]["_tot_wh_exp"] > 0
    assert await hass.config_entries.async_unload(entry.entry_id)
