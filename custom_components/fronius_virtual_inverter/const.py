"""Constants for Fronius Virtual Inverter."""

DOMAIN = "fronius_virtual_inverter"

# Config keys
CONF_PORT = "port"
CONF_UPDATE_INTERVAL = "update_interval"
CONF_SYSTEM_NAME = "system_name"

# P_Grid
CONF_P_GRID_SENSOR = "p_grid_sensor"
CONF_P_GRID_SENSOR_POS = "p_grid_sensor_pos"
CONF_P_GRID_SENSOR_NEG = "p_grid_sensor_neg"
CONF_P_GRID_DUAL_MODE = "p_grid_dual_mode"
CONF_P_GRID_INVERT = "p_grid_invert"

# P_PV
CONF_P_PV_SENSOR = "p_pv_sensor"
CONF_P_PV_INVERT = "p_pv_invert"

# P_Akku
CONF_P_AKKU_SENSOR = "p_akku_sensor"
CONF_P_AKKU_SENSOR_POS = "p_akku_sensor_pos"
CONF_P_AKKU_SENSOR_NEG = "p_akku_sensor_neg"
CONF_P_AKKU_DUAL_MODE = "p_akku_dual_mode"
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

# Modbus TCP Smart Meter IP emulation
CONF_MODBUS_ENABLED = "modbus_enabled"
CONF_MODBUS_PORT = "modbus_port"
DEFAULT_MODBUS_PORT = 502
CONF_MODBUS_ADDRESS = "modbus_address"
DEFAULT_MODBUS_ADDRESS = 240

# Fronius device type for GEN24 hybrid
FRONIUS_DEVICE_TYPE = 1  # DT=1 = Hybrid inverter (GEN24)

# API paths
API_BASE = "/solar_api/v1"
API_POWER_FLOW = f"{API_BASE}/GetPowerFlowRealtimeData.fcgi"
API_INVERTER_INFO = f"{API_BASE}/GetInverterInfo.fcgi"
API_INVERTER_REALTIME = f"{API_BASE}/GetInverterRealtimeData.fcgi"
API_METER_REALTIME = f"{API_BASE}/GetMeterRealtimeData.fcgi"
API_STORAGE_REALTIME = f"{API_BASE}/GetStorageRealtimeData.fcgi"
API_LOGGER_INFO = f"{API_BASE}/GetLoggerInfo.fcgi"
API_VERSION = "/solar_api/GetAPIVersion.cgi"
API_ACTIVE_DEVICE_INFO = "/solar_api/v1/GetActiveDeviceInfo.cgi"

# Grid phase / load balancing
CONF_GRID_PHASES = "grid_phases"
CONF_P_GRID_PHASE_A = "p_grid_phase_a"
CONF_P_GRID_PHASE_B = "p_grid_phase_b"
CONF_P_GRID_PHASE_C = "p_grid_phase_c"
CONF_I_GRID_PHASE_A = "i_grid_phase_a"
CONF_I_GRID_PHASE_B = "i_grid_phase_b"
CONF_I_GRID_PHASE_C = "i_grid_phase_c"
CONF_GRID_CT_RATING = "grid_ct_rating"
DEFAULT_GRID_CT_RATING = 32
CONF_V_GRID_PHASE_A = "v_grid_phase_a"
CONF_V_GRID_PHASE_B = "v_grid_phase_b"
CONF_V_GRID_PHASE_C = "v_grid_phase_c"
DEFAULT_GRID_VOLTAGE = 240.0
CONF_POWER_FACTOR_PHASE_A = "power_factor_phase_a"
CONF_POWER_FACTOR_PHASE_B = "power_factor_phase_b"
CONF_POWER_FACTOR_PHASE_C = "power_factor_phase_c"
CONF_Q_GRID_PHASE_A = "q_grid_phase_a"
CONF_Q_GRID_PHASE_B = "q_grid_phase_b"
CONF_Q_GRID_PHASE_C = "q_grid_phase_c"
