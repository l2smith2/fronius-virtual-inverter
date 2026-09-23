"""Constants for Fronius Virtual Inverter."""

DOMAIN = "fronius_virtual_inverter"

# Entry types — one integration, two kinds of virtual device
CONF_ENTRY_TYPE = "entry_type"
ENTRY_TYPE_INVERTER = "inverter"  # Solar API + mDNS for the Wattpilot (+ optional grid meter)
ENTRY_TYPE_METER = "meter"  # standalone Smart Meter IP (Modbus TCP) for a real Fronius

# General
CONF_PORT = "port"
CONF_UPDATE_INTERVAL = "update_interval"
CONF_SYSTEM_NAME = "system_name"

# P_Grid — for meter entries this is the power flowing through the meter
CONF_P_GRID_SENSOR = "p_grid_sensor"
CONF_P_GRID_IMPORT_SENSOR = "p_grid_import_sensor"
CONF_P_GRID_EXPORT_SENSOR = "p_grid_export_sensor"
CONF_P_GRID_INVERT = "p_grid_invert"

# P_PV
CONF_P_PV_SENSOR = "p_pv_sensor"
CONF_P_PV_INVERT = "p_pv_invert"

# P_Akku (Fronius convention: positive = discharging)
CONF_P_AKKU_SENSOR = "p_akku_sensor"
CONF_P_AKKU_CHARGE_SENSOR = "p_akku_charge_sensor"
CONF_P_AKKU_DISCHARGE_SENSOR = "p_akku_discharge_sensor"
CONF_P_AKKU_INVERT = "p_akku_invert"

# P_Load
CONF_P_LOAD_SENSOR = "p_load_sensor"
CONF_P_LOAD_INVERT = "p_load_invert"

# SOC
CONF_SOC_SENSOR = "soc_sensor"

# Defaults
DEFAULT_PORT = 80
DEFAULT_UPDATE_INTERVAL = 10
DEFAULT_NAME = "fronius-virtual"
DEFAULT_METER_NAME = "ac-battery-meter"

# Modbus TCP Smart Meter IP emulation
CONF_MODBUS_ENABLED = "modbus_enabled"
CONF_MODBUS_PORT = "modbus_port"
DEFAULT_MODBUS_PORT = 502
CONF_MODBUS_ADDRESS = "modbus_address"
DEFAULT_MODBUS_ADDRESS = 240

# Where a standalone virtual meter sits, as configured on the Fronius side
CONF_METER_ROLE = "meter_role"
METER_ROLE_GENERATOR = "generator"  # "External generator" — e.g. an AC-coupled battery
METER_ROLE_LOAD = "load"  # "Consumption path" / subload
METER_ROLE_GRID = "grid"  # "Feed-in point" (primary meter)
METER_ROLES = (METER_ROLE_GENERATOR, METER_ROLE_LOAD, METER_ROLE_GRID)

# Fronius device type for GEN24 hybrid
FRONIUS_DEVICE_TYPE = 1  # DT=1 = Hybrid inverter (GEN24)

# API paths
API_BASE = "/solar_api/v1"
API_POWER_FLOW = f"{API_BASE}/GetPowerFlowRealtimeData.fcgi"
API_INVERTER_INFO = f"{API_BASE}/GetInverterInfo.fcgi"
API_INVERTER_REALTIME = f"{API_BASE}/GetInverterRealtimeData.fcgi"
API_METER_REALTIME = f"{API_BASE}/GetMeterRealtimeData.fcgi"
API_METER_REALTIME_CGI = f"{API_BASE}/GetMeterRealtimeData.cgi"
API_STORAGE_REALTIME = f"{API_BASE}/GetStorageRealtimeData.fcgi"
API_LOGGER_INFO = f"{API_BASE}/GetLoggerInfo.fcgi"
API_VERSION = "/solar_api/GetAPIVersion.cgi"
API_ACTIVE_DEVICE_INFO = f"{API_BASE}/GetActiveDeviceInfo.cgi"

# Grid phase / load balancing
CONF_GRID_PHASES = "grid_phases"
CONF_GRID_CT_RATING = "grid_ct_rating"
DEFAULT_GRID_CT_RATING = 32
DEFAULT_GRID_VOLTAGE = 240.0

# Optional per-phase sensors. Config keys are "<prefix>_phase_<a|b|c>",
# coordinator data keys are "<DATA_PREFIX>_<A|B|C>".
PHASES = ("a", "b", "c")
PHASE_QUANTITIES: dict[str, str] = {
    "p_grid": "P_Grid",  # W
    "i_grid": "I_Grid",  # A
    "v_grid": "V_Grid",  # V
    "power_factor": "PF_Grid",
    "q_grid": "Q_Grid",  # var
}


def phase_key(prefix: str, phase: str) -> str:
    """Config key for a per-phase sensor, e.g. ('p_grid', 'a') -> 'p_grid_phase_a'."""
    return f"{prefix}_phase_{phase}"
