"""Sensor platform — diagnostic entities mirroring what is served."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    PERCENTAGE,
    EntityCategory,
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfEnergy,
    UnitOfPower,
    UnitOfReactivePower,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.loader import async_get_integration

from . import FroniusConfigEntry
from .const import DOMAIN, PHASES
from .coordinator import FroniusVirtualInverterCoordinator


@dataclass(frozen=True, kw_only=True)
class FroniusSensorEntityDescription(SensorEntityDescription):
    """Describe a Fronius virtual inverter sensor."""

    data_key: str
    meter_name: str | None = None  # set = also created for standalone meters, with this name


_POWER: dict[str, Any] = {
    "device_class": SensorDeviceClass.POWER,
    "state_class": SensorStateClass.MEASUREMENT,
    "native_unit_of_measurement": UnitOfPower.WATT,
    "entity_category": EntityCategory.DIAGNOSTIC,
}
_ENERGY: dict[str, Any] = {
    "device_class": SensorDeviceClass.ENERGY,
    "state_class": SensorStateClass.TOTAL_INCREASING,
    "native_unit_of_measurement": UnitOfEnergy.WATT_HOUR,
    "entity_category": EntityCategory.DIAGNOSTIC,
}

# (key prefix, data prefix, name, device class, unit, icon) — one sensor per phase
_PHASE_SENSORS = (
    ("p_grid", "P_Grid", "Grid Power", SensorDeviceClass.POWER, UnitOfPower.WATT, "mdi:transmission-tower"),
    ("i_grid", "I_Grid", "Grid Current", SensorDeviceClass.CURRENT, UnitOfElectricCurrent.AMPERE, "mdi:current-ac"),
    ("v_grid", "V_Grid", "Grid Voltage", SensorDeviceClass.VOLTAGE, UnitOfElectricPotential.VOLT, "mdi:lightning-bolt"),
    ("pf_grid", "PF_Grid", "Grid Power Factor", SensorDeviceClass.POWER_FACTOR, None, "mdi:angle-acute"),
    ("q_grid", "Q_Grid", "Grid Reactive Power", SensorDeviceClass.REACTIVE_POWER, UnitOfReactivePower.VOLT_AMPERE_REACTIVE, "mdi:sine-wave"),
)

SENSOR_DESCRIPTIONS: tuple[FroniusSensorEntityDescription, ...] = (
    FroniusSensorEntityDescription(
        key="p_grid", data_key="P_Grid", name="Grid Power", meter_name="Meter Power",
        icon="mdi:transmission-tower", **_POWER,
    ),
    FroniusSensorEntityDescription(
        key="p_pv", data_key="P_PV", name="PV Power", icon="mdi:solar-power", **_POWER
    ),
    FroniusSensorEntityDescription(
        key="p_akku", data_key="P_Akku", name="Battery Power", icon="mdi:battery-charging", **_POWER
    ),
    FroniusSensorEntityDescription(
        key="p_load", data_key="P_Load", name="Load Power", icon="mdi:home-lightning-bolt", **_POWER
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
        key="e_day", data_key="E_Day", name="Energy Today", icon="mdi:solar-power-variant", **_ENERGY
    ),
    FroniusSensorEntityDescription(
        key="grid_energy_imported",
        data_key="_tot_wh_imp",
        name="Grid Energy Imported",
        meter_name="Energy Imported",
        entity_registry_enabled_default=False,
        icon="mdi:home-import-outline",
        **_ENERGY,
    ),
    FroniusSensorEntityDescription(
        key="grid_energy_exported",
        data_key="_tot_wh_exp",
        name="Grid Energy Exported",
        meter_name="Energy Exported",
        entity_registry_enabled_default=False,
        icon="mdi:home-export-outline",
        **_ENERGY,
    ),
    *(
        FroniusSensorEntityDescription(
            key=f"{key}_{phase}",
            data_key=f"{data_prefix}_{phase.upper()}",
            name=f"{name} Phase {phase.upper()}",
            device_class=device_class,
            state_class=SensorStateClass.MEASUREMENT,
            native_unit_of_measurement=unit,
            entity_category=EntityCategory.DIAGNOSTIC,
            entity_registry_enabled_default=False,
            icon=icon,
        )
        for key, data_prefix, name, device_class, unit, icon in _PHASE_SENSORS
        for phase in PHASES
    ),
    FroniusSensorEntityDescription(
        key="modbus_address",
        data_key="modbus_address",
        name="Modbus Device Address",
        meter_name="Modbus Device Address",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        icon="mdi:ethernet",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: FroniusConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up diagnostic sensors."""
    coordinator = entry.runtime_data
    integration = await async_get_integration(hass, DOMAIN)
    device_info = DeviceInfo(
        identifiers={(DOMAIN, entry.entry_id)},
        name=entry.title,
        manufacturer="Fronius (Virtual)",
        model="Smart Meter IP (Virtual)" if coordinator.is_meter else "GEN24 Virtual Inverter",
        sw_version=str(integration.version),
    )
    async_add_entities(
        FroniusVirtualSensor(coordinator, entry, description, device_info)
        for description in SENSOR_DESCRIPTIONS
        if description.meter_name or not coordinator.is_meter
    )


class FroniusVirtualSensor(CoordinatorEntity[FroniusVirtualInverterCoordinator], SensorEntity):
    """A diagnostic sensor mirroring a value being served."""

    entity_description: FroniusSensorEntityDescription
    _attr_has_entity_name = True
    # Changes every update — keep it out of the recorder database
    _unrecorded_attributes = frozenset({"last_updated"})

    def __init__(
        self,
        coordinator: FroniusVirtualInverterCoordinator,
        entry: FroniusConfigEntry,
        description: FroniusSensorEntityDescription,
        device_info: DeviceInfo,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"
        self._attr_device_info = device_info
        if coordinator.is_meter:
            self._attr_name = description.meter_name

    @property
    def _value(self) -> float | None:
        return (self.coordinator.data or {}).get(self.entity_description.data_key)

    @property
    def available(self) -> bool:
        """Unconfigured values are hidden rather than shown as 0."""
        return super().available and self._value is not None

    @property
    def native_value(self) -> float | None:
        val = self._value
        return None if val is None else round(val, 2)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        last = self.coordinator.last_refresh
        return {"last_updated": last.isoformat() if last else None}
