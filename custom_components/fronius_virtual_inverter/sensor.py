"""Sensor platform for Fronius Virtual Inverter — diagnostic entities."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfEnergy, UnitOfPower, PERCENTAGE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import FroniusVirtualInverterCoordinator


@dataclass(frozen=True)
class FroniusSensorEntityDescription(SensorEntityDescription):
    """Describe a Fronius virtual inverter sensor."""
    data_key: str = ""


SENSOR_DESCRIPTIONS: tuple[FroniusSensorEntityDescription, ...] = (
    FroniusSensorEntityDescription(
        key="p_grid",
        data_key="P_Grid",
        name="Grid Power",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.WATT,
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:transmission-tower",
    ),
    FroniusSensorEntityDescription(
        key="p_pv",
        data_key="P_PV",
        name="PV Power",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.WATT,
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:solar-power",
    ),
    FroniusSensorEntityDescription(
        key="p_akku",
        data_key="P_Akku",
        name="Battery Power",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.WATT,
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:battery-charging",
    ),
    FroniusSensorEntityDescription(
        key="p_load",
        data_key="P_Load",
        name="Load Power",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.WATT,
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:home-lightning-bolt",
    ),
    FroniusSensorEntityDescription(
        key="soc",
        data_key="SOC",
        name="Battery SOC",
        device_class=SensorDeviceClass.BATTERY,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=PERCENTAGE,
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:battery",
    ),
    FroniusSensorEntityDescription(
        key="e_day",
        data_key="E_Day",
        name="Energy Today",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:solar-power-variant",
    ),
    FroniusSensorEntityDescription(
        key="p_grid_a",
        data_key="P_Grid_A",
        name="Grid Power Phase A",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.WATT,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        icon="mdi:transmission-tower",
    ),
    FroniusSensorEntityDescription(
        key="p_grid_b",
        data_key="P_Grid_B",
        name="Grid Power Phase B",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.WATT,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        icon="mdi:transmission-tower",
    ),
    FroniusSensorEntityDescription(
        key="p_grid_c",
        data_key="P_Grid_C",
        name="Grid Power Phase C",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.WATT,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        icon="mdi:transmission-tower",
    ),
    FroniusSensorEntityDescription(
        key="i_grid_a",
        data_key="I_Grid_A",
        name="Grid Current Phase A",
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="A",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        icon="mdi:current-ac",
    ),
    FroniusSensorEntityDescription(
        key="i_grid_b",
        data_key="I_Grid_B",
        name="Grid Current Phase B",
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="A",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        icon="mdi:current-ac",
    ),
    FroniusSensorEntityDescription(
        key="i_grid_c",
        data_key="I_Grid_C",
        name="Grid Current Phase C",
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="A",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        icon="mdi:current-ac",
    ),
    FroniusSensorEntityDescription(
        key="v_grid_a",
        data_key="V_Grid_A",
        name="Grid Voltage Phase A",
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="V",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        icon="mdi:lightning-bolt",
    ),
    FroniusSensorEntityDescription(
        key="v_grid_b",
        data_key="V_Grid_B",
        name="Grid Voltage Phase B",
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="V",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        icon="mdi:lightning-bolt",
    ),
    FroniusSensorEntityDescription(
        key="v_grid_c",
        data_key="V_Grid_C",
        name="Grid Voltage Phase C",
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="V",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        icon="mdi:lightning-bolt",
    ),
    FroniusSensorEntityDescription(
        key="pf_grid_a",
        data_key="PF_Grid_A",
        name="Grid Power Factor Phase A",
        device_class=SensorDeviceClass.POWER_FACTOR,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=None,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        icon="mdi:angle-acute",
    ),
    FroniusSensorEntityDescription(
        key="pf_grid_b",
        data_key="PF_Grid_B",
        name="Grid Power Factor Phase B",
        device_class=SensorDeviceClass.POWER_FACTOR,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=None,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        icon="mdi:angle-acute",
    ),
    FroniusSensorEntityDescription(
        key="pf_grid_c",
        data_key="PF_Grid_C",
        name="Grid Power Factor Phase C",
        device_class=SensorDeviceClass.POWER_FACTOR,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=None,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        icon="mdi:angle-acute",
    ),
    FroniusSensorEntityDescription(
        key="q_grid_a",
        data_key="Q_Grid_A",
        name="Grid Reactive Power Phase A",
        device_class=SensorDeviceClass.REACTIVE_POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="var",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        icon="mdi:sine-wave",
    ),
    FroniusSensorEntityDescription(
        key="q_grid_b",
        data_key="Q_Grid_B",
        name="Grid Reactive Power Phase B",
        device_class=SensorDeviceClass.REACTIVE_POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="var",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        icon="mdi:sine-wave",
    ),
    FroniusSensorEntityDescription(
        key="q_grid_c",
        data_key="Q_Grid_C",
        name="Grid Reactive Power Phase C",
        device_class=SensorDeviceClass.REACTIVE_POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="var",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        icon="mdi:sine-wave",
    ),
    FroniusSensorEntityDescription(
        key="modbus_address",
        data_key="modbus_address",
        name="Modbus Device Address",
        device_class=None,
        state_class=None,
        native_unit_of_measurement=None,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        icon="mdi:ethernet",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Fronius Virtual Inverter sensors."""
    coordinator: FroniusVirtualInverterCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]

    entities = [
        FroniusVirtualSensor(coordinator, entry, description)
        for description in SENSOR_DESCRIPTIONS
    ]
    async_add_entities(entities)


class FroniusVirtualSensor(CoordinatorEntity, SensorEntity):
    """A diagnostic sensor that mirrors data being served to the Wattpilot."""

    entity_description: FroniusSensorEntityDescription

    def __init__(
        self,
        coordinator: FroniusVirtualInverterCoordinator,
        entry: ConfigEntry,
        description: FroniusSensorEntityDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"
        self._attr_name = f"{entry.title} {description.name}"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": entry.title,
            "manufacturer": "Fronius (Virtual)",
            "model": "GEN24 Virtual Inverter",
            "sw_version": "1.0.0",
        }

    @property
    def available(self) -> bool:
        if not self.coordinator.last_update_success:
            return False
        if self.coordinator.data is None:
            return False
        val = self.coordinator.data.get(self.entity_description.data_key)
        return val is not None

    @property
    def native_value(self) -> float | None:
        if self.coordinator.data is None:
            return None
        val = self.coordinator.data.get(self.entity_description.data_key)
        if val is None:
            return None
        return round(val, 2)

    @property
    def extra_state_attributes(self) -> dict:
        t: datetime | None = self.coordinator.last_update_success_time
        return {"last_updated": t.isoformat() if t is not None else None}
