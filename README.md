# Fronius Virtual Inverter

A Home Assistant custom integration that impersonates a **Fronius GEN24 hybrid inverter** on your local network, allowing a **Fronius Wattpilot EV charger** to pair with it and use PV surplus (Eco) charging — without needing real Fronius hardware.

## Why this exists

The Wattpilot's Eco charging mode requires a paired Fronius inverter or Smart Meter IP. Without one, it shows error 109 and won't do surplus charging. This integration serves the Fronius Solar API v1 over HTTP from your HA machine and announces itself via mDNS so the Wattpilot discovers and pairs with it automatically.

## Installation

### HACS (recommended)
1. Add this repo as a custom repository in HACS
2. Install "Fronius Virtual Inverter"
3. Restart Home Assistant

### Manual
1. Copy the `custom_components/fronius_virtual_inverter` folder to `/config/custom_components/`
2. Restart Home Assistant

Then go to **Settings → Devices & Services → Add Integration** and search for "Fronius Virtual Inverter".

## Setup

The integration walks you through four steps:

**Step 1 — Basic settings**
- **Inverter Name**: Used as the mDNS hostname (e.g. `my-inverter` → `my-inverter.local`). Lowercase letters and hyphens only.
- **System Display Name**: Shown in the Wattpilot pairing screen (e.g. `MyHome`). Falls back to inverter name if blank.
- **Port**: HTTP port for the Solar API server (default: `80`). Use a port above 1024 if HA lacks permission to bind port 80.
- **Update Interval**: How often to refresh sensor values (default: 10 seconds).
- **Enable Smart Meter IP (Modbus TCP)**: Also emulates a Fronius Smart Meter IP over Modbus TCP (default port 502, use 5020 if permission is an issue). Useful if you have a real SnapIN inverter on the same network.

**Step 2 — Grid settings**
Map your electricity meter sensor and configure phase settings. Enable the per-phase toggle if your meter provides per-phase data.

**Step 3 — Solar & Battery**
Map solar generation, battery, and house load sensors. All fields are optional.

**Step 4 — Per-phase load balancing (optional)**
Advanced sensors for Wattpilot load balancing accuracy. Only shown if you enabled the toggle in Step 2.

### Sensor sign conventions

| Field | Sign convention | Notes |
|-------|----------------|-------|
| P_Grid | positive = importing, negative = exporting | Grid meter power |
| P_PV | always positive | Solar generation |
| P_Akku | positive = charging, negative = discharging | Battery power |
| P_Load | always negative | House consumption |
| SOC | 0–100% | Battery state of charge |

### Dual sensor mode

If your integration provides separate import and export sensors (e.g. a Shelly 3EM gives `sensor.shelly_active_power_import` and `sensor.shelly_active_power_export` as two positive values), enable **Use Separate Import/Export Sensors** and select both. The integration computes:

```
value = import_sensor - export_sensor
```

### Sign invert

If your sensor reports a signed value with the opposite sign to Fronius convention, enable **Invert Sign**.

## Pairing the Wattpilot

1. With the integration running, open the **Solar.wattpilot** app
2. Go to inverter/charging settings
3. Tap **"Scan for new inverters"**
4. Your virtual inverter should appear (e.g. `MyHome (192.168.1.x)`)
5. Select it and pair

After pairing, the Wattpilot polls your HA machine for live surplus data and adjusts charging accordingly.

## Use cases

### Site A: Fronius inverter with battery storage

You have an existing Fronius SnapIN inverter already integrated in HA, plus a third-party battery. Map the sensors from the Fronius integration directly:

- **P_Grid**: `sensor.fronius_power_grid` (already signed correctly)
- **P_PV**: `sensor.fronius_power_photovoltaics`
- **P_Akku**: Use dual sensor mode with your battery's charge/discharge sensors
- **SOC**: Your battery's state of charge sensor

For load balancing, map the per-phase sensors from your Fronius Smart Meter:
- `sensor.fronius_current_phase_1` / `_2` / `_3`
- `sensor.fronius_power_factor_phase_1` / `_2` / `_3`
- `sensor.fronius_reactive_power_phase_1` / `_2` / `_3`

### Site B: Third-party inverter, no Fronius hardware

You have a non-Fronius inverter (e.g. Growatt, SolarEdge, Enphase) and a separate energy meter. The Wattpilot has no inverter to pair with — this integration provides that.

- **P_Grid**: Your energy meter sensor (e.g. Shelly 3EM in dual sensor mode)
- **P_PV**: Your inverter's output power sensor
- **P_Akku**: Leave blank if no battery
- **SOC**: Leave blank if no battery

## Diagnostic sensors

The integration exposes diagnostic entities in HA showing exactly what it's serving to the Wattpilot:

- `sensor.<name>_grid_power` — P_Grid (W)
- `sensor.<name>_pv_power` — P_PV (W)
- `sensor.<name>_battery_power` — P_Akku (W)
- `sensor.<name>_load_power` — P_Load (W)
- `sensor.<name>_battery_soc` — SOC (%)
- `sensor.<name>_energy_today` — daily PV accumulator (Wh)
- Per-phase power, current, voltage, power factor, reactive power (when configured)

Sensors for unconfigured fields are hidden automatically.

## Troubleshooting

**Wattpilot doesn't find the inverter during scan:**
- Ensure HA and the Wattpilot are on the same subnet — mDNS does not cross subnet boundaries
- Check that the configured port is reachable: open `http://<ha-ip>:<port>/solar_api/v1/GetPowerFlowRealtimeData.fcgi` in a browser — you should get JSON
- If running HA in a VM or container, check that multicast is not being filtered (disable multicast snooping on the bridge interface)

**Error 109 persists after pairing:**
- The Wattpilot may cache the old "no inverter" state. Power-cycle the Wattpilot.
- Check the Wattpilot is polling the correct HA IP address

**Wattpilot load balancing shows "not available":**
- Configure the per-phase sensors (Step 4). Without them, load balancing falls back to equal phase splitting.
- If you have a Fronius Smart Meter, map the `power_factor_phase_*` and `reactive_power_phase_*` sensors — current alone at near-zero real power gives unstable power factor readings.

**Sensors show unavailable:**
- Check the mapped entity IDs exist and have numeric states in Developer Tools → States
- Check HA logs for errors from `fronius_virtual_inverter`

## Architecture

```
Home Assistant sensors
        │
        ▼
FroniusVirtualInverterCoordinator   (reads sensors every N seconds)
        │
        ├── FroniusSolarAPIServer   (aiohttp HTTP server)
        │       ├── GET /solar_api/v1/GetPowerFlowRealtimeData.fcgi  ◄── Wattpilot polls this
        │       ├── GET /solar_api/v1/GetMeterRealtimeData.cgi       ◄── Wattpilot load balancing
        │       ├── GET /solar_api/v1/GetInverterInfo.fcgi
        │       └── GET /solar_api/v1/GetStorageRealtimeData.fcgi
        │
        ├── RawMDNSAnnouncer        (raw UDP mDNS multicast)
        │       ◄── Wattpilot discovers _Fronius-SE-Inverter._tcp.local.
        │
        └── FroniusModbusServer     (Modbus TCP, optional)
                ◄── Real SnapIN inverter polls for Smart Meter IP data
```
