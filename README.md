# Fronius Virtual Inverter

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

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

Primarily a **Fronius inverter emulator** (HTTP Solar API v1) so the Wattpilot can discover and pair with it directly — with optional **Fronius Smart Meter IP emulation** (Modbus TCP) as a secondary feature for real Fronius hardware.

- Wattpilot discovery and pairing via raw mDNS multicast (IPv4 + IPv6)
- Fronius Solar API v1 HTTP server with all endpoints the Wattpilot polls
- Per-phase load balancing data (`GetMeterRealtimeData`) for accurate phase-aware charging
- Flexible sensor mapping: signed sensors, separate import/export sensors, sign invert
- Automatic unit conversion: kW→W, kWh→Wh, MW→W, MWh→Wh
- Diagnostic HA sensors showing exactly what is being served to the Wattpilot
- Unconfigured sensors hidden automatically (not shown as unavailable)
- Human-readable display name shown in the Wattpilot pairing screen
- Optional: Modbus TCP Smart Meter IP emulation (SunSpec float model 213) for real Fronius inverters

---

## Compatibility

- Tested with **Wattpilot V2**, firmware **42.5**
- Requires **Home Assistant 2026.3+**
- Works with any inverter or energy meter that has HA sensors

---

## Installation

### HACS (Recommended)

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=l2smith2&repository=fronius-virtual-inverter&category=integration)

Or manually:
1. Open HACS in Home Assistant
2. Go to **Integrations**
3. Click the **⋮** menu (top right) → **Custom repositories**
4. Add `https://github.com/l2smith2/fronius-virtual-inverter` with category **Integration**
5. Find **Fronius Virtual Inverter** in the HACS integrations list and click **Download**
6. Restart Home Assistant

*Note: This integration is pending approval for the official HACS default store. Once approved, it will be directly searchable in HACS without adding a custom repository.*

### Manual Installation

1. Download the [latest release](https://github.com/l2smith2/fronius-virtual-inverter/releases/latest)
2. Extract the `custom_components/fronius_virtual_inverter` folder
3. Copy it to your Home Assistant `config/custom_components/` directory
4. Restart Home Assistant

### Setup

1. Go to **Settings → Devices & Services → Add Integration**
2. Search for **Fronius Virtual Inverter**
3. Follow the configuration steps

---

## Configuration

### Minimum setup (PV surplus charging only)

Just two sensors are required:
- **Grid Power Sensor** — your grid import/export power
- **Solar Power Sensor** — your PV generation power

That's it — the Wattpilot will discover the virtual inverter and PV surplus
(Eco) charging will work.

### Recommended additions

- **Battery SOC Sensor** — unlocks PV Battery threshold controls in the
  Wattpilot app (Charges from / Discharges until). Works with any battery
  brand exposed in Home Assistant — Tesla Powerwall, BYD, Pylontech, etc.
- **Battery Power Sensor** — reports battery charge/discharge power
- **Grid Circuit Breaker Rating** — set this to your actual supply limit
  (default 32A) so the Wattpilot never exceeds it even without load balancing

### Advanced: Per-phase load balancing

Without per-phase sensors, the Wattpilot charges safely up to your configured
Circuit Breaker Rating but can't dynamically respond to other loads turning
on/off in the house. Adding per-phase Current, Voltage, Power Factor, and
Reactive Power sensors (from a smart meter like a Shelly 3EM or Fronius
Smart Meter) unlocks full dynamic load balancing.

### Optional: Smart Meter IP emulation (Modbus TCP)

This integration primarily emulates a **Fronius inverter** so the Wattpilot
can pair with it directly over HTTP. It can *also* emulate a **Fronius
Smart Meter IP** over Modbus TCP (port 502) — useful if you have a real
Fronius inverter (GEN24, SnapIN) that needs grid meter data sourced from
Home Assistant sensors, independent of the Wattpilot pairing. Most users
with no existing Fronius hardware won't need this.

---

### Setup flow reference

**Step 1 — Basic Setup**
Inverter Name, System Display Name, HTTP Server Port, Update Interval.

**Step 2 — Required: Grid & Solar**
- **Grid Power Sensor** *(required)* — positive = importing, negative = exporting
- **Solar Power Sensor** *(required)* — PV generation
- Grid Phase Configuration, Circuit Breaker Rating
- **Enable per-phase load balancing sensors** — optional toggle; if enabled, Steps 4/5 are shown

**Step 3 — Optional: Battery & Load**
Battery SOC, Battery Power, House Consumption. All optional — leave blank if not available.

**Step 4 — Optional: Load Balancing — Phase A** *(shown only if toggled in Step 2)*
Phase A power, current, voltage, power factor, reactive power.

**Step 5 — Optional: Load Balancing — Phases B & C** *(three-phase only)*
Phase B and C sensors.

**Step 6 — Optional: Smart Meter IP Emulation (Modbus TCP)**
Enable Modbus, configure port and unit ID.

All steps are available again under **Settings → Devices & Services → Configure**.

### Sensor sign conventions

| Field | Sign convention | Notes |
|-------|----------------|-------|
| Grid Power | positive = importing, negative = exporting | Grid meter power |
| Solar Generation | always positive | Solar panel output |
| Battery Power | positive = charging, negative = discharging | Battery power |
| House Consumption | always negative | House load |
| Battery State of Charge | 0–100% | Battery percentage |

### Dual sensor mode

If your meter provides separate import and export sensors (e.g. a Shelly 3EM gives two positive values), enable **Use Separate Import/Export Sensors** and select both. The integration computes `import − export` internally.

### Sign invert

If your sensor reports a signed value with the opposite sign to Fronius convention, enable the invert toggle for that field (e.g. **Invert Grid Sign**, **Invert Solar Sign**, **Invert Battery Sign**).

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

- **Grid Power Sensor** — `sensor.fronius_power_grid` (already signed correctly)
- **Solar Generation Sensor** — `sensor.fronius_power_photovoltaics`
- **Battery Power Sensor** — enable **Use Separate Charge/Discharge Sensors** with your battery's charge/discharge sensors
- **Battery State of Charge** — your battery's state of charge sensor

For load balancing, map the per-phase sensors from your Fronius Smart Meter:

- `sensor.fronius_current_phase_1` / `_2` / `_3`
- `sensor.fronius_power_factor_phase_1` / `_2` / `_3`
- `sensor.fronius_reactive_power_phase_1` / `_2` / `_3`

You can also enable Modbus TCP emulation (Step 6) to give the SnapIN a virtual grid meter if needed.

### Site with a third-party inverter and no Fronius hardware

You have a non-Fronius inverter (e.g. Growatt, SolarEdge, Enphase) and a separate energy meter. The Wattpilot has no inverter to pair with — this integration provides that.

- **Grid Power Sensor** — your energy meter (e.g. Shelly 3EM; enable **Use Separate Import/Export Sensors** for dual readings)
- **Solar Generation Sensor** — your inverter's output power sensor
- **Battery Power Sensor** — leave blank if no battery
- **Battery State of Charge** — leave blank if no battery

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

- `sensor.<name>_grid_power` — Grid Power (W)
- `sensor.<name>_pv_power` — Solar Generation (W)
- `sensor.<name>_battery_power` — Battery Power (W)
- `sensor.<name>_load_power` — House Consumption (W)
- `sensor.<name>_battery_soc` — Battery State of Charge (%)
- `sensor.<name>_energy_today` — daily PV accumulator (Wh)
- `sensor.<name>_grid_energy_imported` — cumulative grid import (Wh) — disabled by default; enable to add to Energy dashboard
- `sensor.<name>_grid_energy_exported` — cumulative grid export (Wh) — disabled by default; enable to add to Energy dashboard
- `sensor.<name>_modbus_address` — Modbus Device Address
- Per-phase power, current, voltage, power factor, and reactive power (when configured)

Sensors for unconfigured fields are hidden automatically.

---

## Known Issues

### Sensors become unavailable when enabling new diagnostic entities
When enabling a previously-disabled diagnostic sensor (e.g. per-phase sensors),
all integration sensors may become unavailable. This is a known issue
with the current coordinator implementation. A full Home Assistant restart
resolves it. This will be fixed in a future release.

### "P_Grid is null" error when switching pairing
If the Wattpilot is currently paired with another inverter (e.g. a real Fronius
SnapIN), attempting to pair with the virtual inverter while the old pairing is
still active may show "An error occurred — P_Grid is null".
**Fix:** Fully unpair from the existing inverter first, wait a few seconds,
then pair with the virtual inverter. This is a Wattpilot app limitation, not
an issue with the virtual inverter itself.

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
- If you have a Fronius Smart Meter, also map **Power Factor Phase A/B/C** and **Reactive Power Phase A/B/C** — current alone at near-zero real power gives unstable power factor readings

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
