"""Constants for Fronius Virtual Inverter."""

DOMAIN = "fronius_virtual_inverter"

# Config keys
CONF_PORT = "port"
CONF_UPDATE_INTERVAL = "update_interval"

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
DEFAULT_PORT = 8484
DEFAULT_UPDATE_INTERVAL = 10
DEFAULT_NAME = "fronius-virtual"

# Modbus TCP Smart Meter IP emulation
CONF_MODBUS_ENABLED = "modbus_enabled"
CONF_MODBUS_PORT = "modbus_port"
DEFAULT_MODBUS_PORT = 502
DEFAULT_MODBUS_PORT_ALT = 5020  # non-privileged fallback if 502 not available

# mDNS
MDNS_SERVICE_TYPE = "_http._tcp.local."
MDNS_FRONIUS_TYPE = "_fronius-symo._tcp.local."

# Fronius device type for GEN24 hybrid
FRONIUS_DEVICE_TYPE = 1  # DT=1 = Hybrid inverter (GEN24)
FRONIUS_SOFTWARE_VERSION = "1.14.1-3"
FRONIUS_HARDWARE_VERSION = "2.4E"
FRONIUS_SERIAL = "12345678"  # will be overridden per entry

# API paths
API_BASE = "/solar_api/v1"
API_POWER_FLOW = f"{API_BASE}/GetPowerFlowRealtimeData.fcgi"
API_INVERTER_INFO = f"{API_BASE}/GetInverterInfo.fcgi"
API_INVERTER_REALTIME = f"{API_BASE}/GetInverterRealtimeData.fcgi"
API_METER_REALTIME = f"{API_BASE}/GetMeterRealtimeData.fcgi"
API_STORAGE_REALTIME = f"{API_BASE}/GetStorageRealtimeData.fcgi"
API_VERSION = "/solar_api/GetAPIVersion.cgi"
