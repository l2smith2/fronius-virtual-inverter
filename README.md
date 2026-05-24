# fronius_virtual_inverter

A Home Assistant custom integration that impersonates a **Fronius GEN24 hybrid inverter** on your local network, allowing a **Fronius Wattpilot EV charger** to pair with it and use PV surplus (Eco) charging — without needing real Fronius hardware.

## Why this exists

The Wattpilot's Eco charging mode requires a paired Fronius inverter or Smart Meter IP. Without one, it shows error 109 and won't do surplus charging. This integration serves the Fronius Solar API v1 over HTTP from a real port on your HA machine, and announces itself via mDNS so the Wattpilot discovers and pairs with it.

## Installation

1. Copy the `fronius_virtual_inverter` folder to `/config/custom_components/`
2. Restart Home Assistant
3. Go to **Settings → Devices & Services → Add Integration** and search for "Fronius Virtual Inverter"

## Setup

**Step 1 — Basic settings:**
- **Inverter Name**: Used as the mDNS hostname (e.g. `fronius-virtual` → `fronius-virtual.local`). Use lowercase letters and hyphens only.
- **Port**: HTTP port the Solar API server listens on (default: `8484`). Must not conflict with other services.
- **Update Interval**: How often to refresh sensor values (default: 10 seconds).

**Step 2 — Sensor mapping:**

Map your HA sensors to the Fronius power flow fields. All fields are optional — leave blank if not available.

| Field | Fronius sign convention | Notes |
|-------|------------------------|-------|
| P_Grid | negative = export to grid, positive = import | Grid meter power |
| P_PV | always positive | Solar generation |
| P_Akku | negative = discharging, positive = charging | Battery power |
| P_Load | always negative | Site consumption |
| SOC | 0–100% | Battery state of charge |

### Dual sensor mode

If your integration provides separate sensors for import and export (e.g. a Shelly 3EM gives you `sensor.shelly_active_power_import` and `sensor.shelly_active_power_export` as two positive values), enable **Dual sensor mode** for that field and select both sensors. The integration computes:

```
value = pos_sensor - neg_sensor
```

So for P_Grid: `import_W - export_W` → positive when importing, negative when exporting. ✓

### Sign invert

If your sensor already reports a signed value but with the opposite sign to what Fronius expects, enable **Invert sign**.

## Pairing the Wattpilot

1. With the integration running, open the **Solar.wattpilot** app
2. Go to the inverter/charging settings
3. Tap **"Scan for new inverters"**
4. Your virtual inverter (`fronius-virtual.local` or whatever name you chose) should appear
5. Select it and pair

After pairing, the Wattpilot will poll `http://<ha-ip>:8484/solar_api/v1/GetPowerFlowRealtimeData.fcgi` for live surplus data.

## Use cases

### My setup (SnapIN + Powerwalls)
- P_PV: `sensor.fronius_power_photovoltaics`
- P_Grid: `sensor.fronius_power_grid` (already signed correctly)
- P_Akku: use dual mode — charge sensor from Tesla Gateway, discharge sensor from Tesla Gateway
- SOC: `sensor.powerwall_battery_percent`

### Mum's setup (Growatt + Shelly 3EM, no battery)
- P_Grid: dual mode — `sensor.shelly_active_power_import` / `sensor.shelly_active_power_export`
- P_PV: `sensor.growatt_output_power`
- P_Akku: leave blank
- SOC: leave blank

## Diagnostic sensors

The integration exposes diagnostic sensor entities in HA showing exactly what it's serving to the Wattpilot:
- `sensor.<name>_grid_power`
- `sensor.<name>_pv_power`
- `sensor.<name>_battery_power`
- `sensor.<name>_load_power`
- `sensor.<name>_battery_soc`
- `sensor.<name>_energy_today`

## Troubleshooting

**Wattpilot doesn't find the inverter during scan:**
- Ensure HA and the Wattpilot are on the same subnet (mDNS doesn't cross subnet boundaries)
- Check that port 8484 (or your chosen port) is not blocked by firewall
- Try accessing `http://<ha-ip>:8484/solar_api/v1/GetPowerFlowRealtimeData.fcgi` in a browser — you should get JSON

**Error 109 persists after pairing:**
- The Wattpilot may cache the old "no inverter" state. Try power-cycling the Wattpilot.
- Check the Wattpilot is polling the correct IP (your HA IP, not a cached old inverter IP)

**Sensors show unavailable:**
- Check the mapped entity IDs exist and have numeric states in Developer Tools → States
- Check HA logs for warnings from `fronius_virtual_inverter`

## Architecture

```
Home Assistant sensors
        │
        ▼
FroniusVirtualInverterCoordinator   (reads sensors every N seconds)
        │
        ├── FroniusSolarAPIServer   (aiohttp on port 8484)
        │       ├── GET /solar_api/v1/GetPowerFlowRealtimeData.fcgi  ◄── Wattpilot polls this
        │       ├── GET /solar_api/v1/GetInverterInfo.fcgi
        │       ├── GET /solar_api/v1/GetInverterRealtimeData.fcgi
        │       └── GET /solar_api/v1/GetStorageRealtimeData.fcgi
        │
        └── FroniusMDNSAnnouncer    (zeroconf _http._tcp.local.)
                                     ◄── Wattpilot discovers this
```
