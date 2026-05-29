# Fronius Virtual Inverter

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)

A Home Assistant custom integration that emulates a Fronius inverter and Smart Meter IP, enabling Fronius Wattpilot PV surplus charging without real Fronius hardware.

---

## ☕ Support

If this integration saves you energy (and it will), consider buying me a coffee!

[![Buy Me A Coffee](https://img.shields.io/badge/Buy%20Me%20A%20Coffee-l2smith2-yellow?style=flat-square&logo=buy-me-a-coffee)](https://www.buymeacoffee.com/l2smith2)

---

## ⚠️ Vibe Coded

This integration was entirely designed and built using AI-assisted development
(Claude by Anthropic) across multiple chat and Claude Code sessions.
It has been tested on real hardware but may contain bugs. Use at your own risk.
Pull requests and issues welcome.

### Energy footprint

The AI compute used to build this integration consumed an estimated **1–15 kWh**
of electricity (roughly equivalent to 5–60 minutes of EV charging at 11 kW).
A Wattpilot configured with this integration in Eco mode will typically offset
that energy cost within **the first sunny day** of PV surplus charging.

---

## What it does

The Wattpilot's Eco (PV surplus) charging mode requires a paired Fronius inverter or Smart Meter IP. Without one it shows error 109 and won't do surplus charging. This integration solves that by:

- **Emulating a Fronius GEN24 inverter** over HTTP (Fronius Solar API v1), so the Wattpilot can pair and receive live power flow data
- **Announcing itself via mDNS** so the Wattpilot discovers it automatically on the local network
- **Optionally emulating a Fronius Smart Meter IP** over Modbus TCP, useful if you have a real Fronius SnapIN inverter that needs a grid meter
- **Reading live data from your existing HA sensors** — grid power, solar generation, battery, house load, and per-phase values for load balancing

---

## Features

- Wattpilot discovery and pairing via raw mDNS multicast (IPv4 + IPv6)
- Fronius Solar API v1 HTTP server with all endpoints the Wattpilot polls
- Per-phase load balancing data (`GetMeterRealtimeData`) for accurate phase-aware charging
- Optional Modbus TCP Smart Meter IP emulation (SunSpec float model 213, unit ID 240)
- Flexible sensor mapping: signed sensors, separate import/export sensors, sign invert
- Automatic unit conversion: kW→W, kWh→Wh, MW→W, MWh→Wh
- Diagnostic HA sensors showing exactly what is being served to the Wattpilot
- Unconfigured sensors hidden automatically (not shown as unavailable)
- Human-readable display name shown in the Wattpilot pairing screen

---

## Compatibility

- Tested with **Wattpilot V2**, firmware **42.5**
- Requires **Home Assistant 2026.3+**
- Works with any inverter or energy meter that has HA sensors

---

## Installation

### HACS (recommended)

1. In HACS, go to **Integrations → ⋮ → Custom repositories**
2. Add `https://github.com/l2smith2/fronius-virtual-inverter` as an **Integration**
3. Search for "Fronius Virtual Inverter" and install
4. Restart Home Assistant

### Manual

1. Copy the `custom_components/fronius_virtual_inverter` folder to `/config/custom_components/`
2. Restart Home Assistant

Then go to **Settings → Devices & Services → Add Integration** and search for **Fronius Virtual Inverter**.

---

## Configuration

Setup is a guided multi-step flow:

**Step 1 — Basic settings**
- **Inverter Name** — mDNS hostname (e.g. `my-inverter` → `my-inverter.local`). Lowercase letters and hyphens only.
- **System Display Name** — shown in the Wattpilot pairing screen (e.g. `MyHome`). Falls back to inverter name if blank.
- **Port** — HTTP port for the Solar API server (default: `80`). Use a port above 1024 if HA lacks permission to bind 80.
- **Update Interval** — how often to refresh sensor values (default: 10 seconds).

**Step 2 — Grid settings**
Map your electricity meter sensor, set phase count (single/three-phase), circuit breaker rating, and optionally enable the per-phase sensor steps for Wattpilot load balancing.

**Step 3 — Solar & Battery**
Map solar generation, battery charge/discharge, house load, and battery state of charge sensors. All fields are optional. The **Battery State of Charge** field accepts any HA sensor reporting 0–100% — it does not need to come from a Fronius battery. Mapping a SOC sensor unlocks the battery threshold controls in the Solar.wattpilot app (Charges from, Discharges until, Discharges until (boost)).

**Step 4 — Per-phase load balancing — Phase A** *(optional)*
Phase A power, current, voltage, power factor, and reactive power sensors. Only shown if you enabled the per-phase toggle in Step 2.

**Step 5 — Per-phase load balancing — Phases B & C** *(optional, three-phase only)*
Phase B and C sensors. Only shown if three-phase is selected.

**Step 6 — Advanced options**
Enable Modbus TCP Smart Meter IP emulation and set the Modbus port (default: 502).

All steps are available again under **Settings → Devices & Services → Configure**.

### Sensor sign conventions

| Field | Sign convention | Notes |
|-------|----------------|-------|
| P_Grid | positive = importing, negative = exporting | Grid meter power |
| P_PV | always positive | Solar generation |
| P_Akku | positive = charging, negative = discharging | Battery power |
| P_Load | always negative | House consumption |
| SOC | 0–100% | Battery state of charge |

### Dual sensor mode

If your meter provides separate import and export sensors (e.g. a Shelly 3EM gives two positive values), enable **Use Separate Import/Export Sensors** and select both. The integration computes `import − export` internally.

### Sign invert

If your sensor reports a signed value with the opposite sign to Fronius convention, enable **Invert Sign**.

---

## Pairing the Wattpilot

1. With the integration running, open the **Solar.wattpilot** app
2. Go to inverter / charging settings
3. Tap **"Scan for new inverters"**
4. Your virtual inverter should appear (e.g. `MyHome (192.168.1.x)`)
5. Select it and pair

After pairing the Wattpilot polls your HA machine for live surplus data and adjusts charging accordingly.

---

## Use cases

### Site with an existing Fronius SnapIN inverter

You already have a Fronius inverter integrated in HA via the Fronius integration, plus a third-party battery. The Wattpilot needs to see battery SOC and per-phase load data that the SnapIN can't provide directly.

Map sensors from the Fronius HA integration:

- **P_Grid** — `sensor.fronius_power_grid` (already signed correctly)
- **P_PV** — `sensor.fronius_power_photovoltaics`
- **P_Akku** — use dual sensor mode with your battery's charge/discharge sensors
- **SOC** — your battery's state of charge sensor

For load balancing, map the per-phase sensors from your Fronius Smart Meter:

- `sensor.fronius_current_phase_1` / `_2` / `_3`
- `sensor.fronius_power_factor_phase_1` / `_2` / `_3`
- `sensor.fronius_reactive_power_phase_1` / `_2` / `_3`

You can also enable Modbus TCP emulation (Step 6) to give the SnapIN a virtual grid meter if needed.

### Site with a third-party inverter and no Fronius hardware

You have a non-Fronius inverter (e.g. Growatt, SolarEdge, Enphase) and a separate energy meter. The Wattpilot has no inverter to pair with — this integration provides that.

- **P_Grid** — your energy meter sensor (e.g. Shelly 3EM in dual sensor mode)
- **P_PV** — your inverter's output power sensor
- **P_Akku** — leave blank if no battery
- **SOC** — leave blank if no battery

### Battery SOC from third-party systems

By mapping a battery SOC sensor from any third-party battery system (e.g. Tesla Powerwall,
BYD, Pylontech via a compatible HA integration), the Wattpilot's **PV Battery** functions
are unlocked:

- **Charges from** — minimum SOC before Wattpilot starts using battery power for charging
- **Discharges until** — SOC threshold below which the Wattpilot stops discharging battery
- **Discharges until (boost)** — SOC threshold for boost mode

This works with any battery that exposes a state of charge sensor in Home Assistant,
regardless of brand or inverter manufacturer.

---

## Diagnostic sensors

The integration exposes diagnostic entities in HA showing exactly what is being served to the Wattpilot:

- `sensor.<name>_grid_power` — P_Grid (W)
- `sensor.<name>_pv_power` — P_PV (W)
- `sensor.<name>_battery_power` — P_Akku (W)
- `sensor.<name>_load_power` — P_Load (W)
- `sensor.<name>_battery_soc` — SOC (%)
- `sensor.<name>_energy_today` — daily PV accumulator (Wh)
- Per-phase power, current, voltage, power factor, and reactive power (when configured)

Sensors for unconfigured fields are hidden automatically.

---

## Troubleshooting

**Wattpilot doesn't find the inverter during scan**
- Ensure HA and the Wattpilot are on the same subnet — mDNS does not cross subnet boundaries
- Check the port is reachable: open `http://<ha-ip>:<port>/solar_api/v1/GetPowerFlowRealtimeData.fcgi` in a browser — you should get JSON
- If running HA in a VM or container, check that multicast is not being filtered (disable multicast snooping on the bridge interface)

**Error 109 persists after pairing**
- The Wattpilot may cache the old "no inverter" state — power-cycle the Wattpilot
- Check the Wattpilot is polling the correct HA IP address

**Wattpilot load balancing shows "not available"**
- Configure the per-phase sensors (Steps 4/5). Without them, load balancing falls back to equal phase splitting.
- If you have a Fronius Smart Meter, also map `power_factor_phase_*` and `reactive_power_phase_*` — current alone at near-zero real power gives unstable power factor readings

**Sensors show unavailable**
- Check the mapped entity IDs exist and have numeric states in Developer Tools → States
- Check HA logs for errors from `fronius_virtual_inverter`

---

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
        ├── RawMDNSAnnouncer        (raw UDP mDNS multicast, IPv4 + IPv6)
        │       ◄── Wattpilot discovers _Fronius-SE-Inverter._tcp.local.
        │
        └── FroniusModbusServer     (Modbus TCP, optional)
                ◄── Real SnapIN inverter polls for Smart Meter IP data
```

---

## Credits & References

This integration would not exist without the prior work and research from:

- **[joscha82/wattpilot](https://github.com/joscha82/wattpilot)** — Wattpilot WebSocket API reverse engineering and documentation
- **[ruaan-deysel/ha-wattpilot](https://github.com/ruaan-deysel/ha-wattpilot)** — Fronius Wattpilot Home Assistant integration
- **[americanium/fronius_sm_simulator](https://github.com/americanium/fronius_sm_simulator)** — Fronius Smart Meter Modbus TCP simulator
- **[Ralim/fronius_meter_emulation](https://github.com/Ralim/fronius_meter_emulation)** — Fronius meter emulation research
- **[Photovoltaikforum — Fronius Smart Meter TCP Protokoll](https://www.photovoltaikforum.com/thread/185108-fronius-smart-meter-tcp-protokoll/)** — Community research on Modbus TCP register maps and GEN24 meter discovery
- **[Photovoltaikforum — Gen24 Smart Meter Modbus TCP Emulation mit ESP32](https://www.photovoltaikforum.com/thread/224214-gen24-smart-meter-modbus-tcp-emulation-mit-esp32/)** — ESP32 implementation that confirmed the working register map and Wattpilot compatibility
- **Fronius Solar API V1 documentation** — Official Fronius API specification
- **Fronius Smart Meter Register Map (Float)** — Official Fronius Modbus register documentation

Special thanks to the Home Assistant community and Anthropic's Claude for making this possible.
