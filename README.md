# Fronius Virtual Inverter

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

A Home Assistant custom integration that emulates a Fronius inverter and Smart Meter IP, enabling Fronius Wattpilot PV surplus charging without real Fronius hardware — and lets a real Fronius inverter read Home Assistant sensors as extra Smart Meter IP meters, e.g. an AC-coupled battery as an external generator.

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
- **Emulating Fronius Smart Meter IPs** over Modbus TCP for real Fronius inverters — the grid meter, and as many secondary meters as you like (e.g. an AC-coupled battery at the *external generator* position)
- **Reading live data from your existing HA sensors** — grid power, solar generation, battery, house load, and per-phase values for load balancing

---

## Features

- Two kinds of device, added independently:
  - **Virtual inverter** — for the Wattpilot (HTTP Solar API + mDNS), with an optional Smart Meter IP grid meter
  - **Virtual smart meter** — a standalone Smart Meter IP for a real Fronius inverter
- Wattpilot discovery and pairing via raw mDNS multicast (IPv4 + IPv6)
- Fronius Solar API v1 HTTP server with all endpoints the Wattpilot polls
- Per-phase load balancing data (`GetMeterRealtimeData`) for accurate phase-aware charging
- Several virtual meters share one Modbus TCP port, each with its own unit ID (e.g. grid meter 240, battery meter 241 — both on HA-IP:502)
- Flexible sensor mapping: signed sensors, separate import/export (or charge/discharge) sensors, sign invert
- Automatic unit conversion: kW→W, kWh→Wh, MW→W, MWh→Wh, kvar→var, % power factor→fraction
- Energy counters survive restarts, so Fronius/Solar.web never see a meter count backwards
- Diagnostic HA sensors showing exactly what is being served
- Unconfigured sensors hidden automatically (not shown as unavailable)
- Human-readable display name shown in the Wattpilot pairing screen
- Every setting can be changed later from **Configure**, one section at a time

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
3. Choose **Virtual inverter** (for a Wattpilot) or **Virtual smart meter** (for a real Fronius inverter) and follow the steps

---

## Configuration

### Virtual inverter — setup

**Step 1 — Virtual inverter:** hostname (also the mDNS name, `<hostname>.local`), display name (shown when pairing the Wattpilot, e.g. `MyHome`), HTTP port.

**Step 2 — Grid & solar** *(required)*
- **Grid power sensor** — positive = importing, negative = exporting. If your meter reports import and export as two positive sensors, open **Separate import/export sensors** instead.
- **Solar power sensor** — PV generation
- **Grid connection** (single or three phase) and **Main breaker rating** — the breaker rating is reported to the Wattpilot as its maximum current, so it never exceeds your supply even without load balancing

**Step 3 — Battery & house load** *(optional)*
- **Battery state of charge** — unlocks the Wattpilot's PV Battery thresholds (Charges from / Discharges until). Works with any battery brand.
- **Battery power** — positive = discharging (Fronius convention), or open **Separate charge/discharge sensors**
- **House consumption**

That's all PV surplus charging needs. The Wattpilot will discover the virtual inverter.

### Changing settings later

**Settings → Devices & Services → Fronius Virtual Inverter → Configure** opens a menu. Pick one section, change it, save — no need to step through the rest:

| Virtual inverter | Virtual smart meter |
|---|---|
| General — display name, HTTP port, update interval | Meter — position, Modbus port & unit ID, update interval |
| Grid & solar sensors | Meter power sensor |
| Battery & house load | |
| Load balancing — per-phase sensors | |
| Smart Meter IP (Modbus TCP) | |

Clearing a field removes that sensor. The hostname can't be changed (it's the device's identity); rename the entry in HA if you just want a different label.

### Per-phase load balancing

Without per-phase sensors, the Wattpilot charges safely up to your configured
Main breaker rating but can't dynamically respond to other loads turning
on/off in the house. Adding per-phase Current, Voltage, Power Factor, and
Reactive Power sensors (from a smart meter like a Shelly 3EM or Fronius
Smart Meter) under **Configure → Load balancing** unlocks full dynamic load
balancing. Phases B and C appear once the grid connection is set to three phase.

### Smart Meter IP for your grid (Modbus TCP)

**Configure → Smart Meter IP** makes the virtual inverter also serve its grid
values as a **Fronius Smart Meter IP** on port 502 (unit ID 240) — useful if you
have a real Fronius inverter (GEN24, SnapIN) that needs grid meter data sourced
from Home Assistant sensors. Most users with no existing Fronius hardware
won't need this.

### Virtual smart meter — AC-coupled battery as an external generator

A Fronius inverter only knows what its own meters measure. An AC-coupled
battery (Tesla Powerwall, a second inverter's battery, …) is invisible to it,
so Fronius' house consumption and Solar.web figures are wrong by whatever the
battery is doing. A secondary meter at the **external generator** position,
reporting the battery's power, fixes that.

**In Home Assistant**
1. **Add Integration → Fronius Virtual Inverter → Virtual smart meter**
2. Name it (e.g. `AC Battery` — also its serial number), choose **Meter position: External generator**, keep port **502**, and keep the suggested unit ID (**241** when your grid meter is on 240). Both meters share HA-IP:502.
3. Pick your **battery power sensor** — positive while discharging. If your battery has separate charge and discharge sensors, open **Separate inflow/outflow sensors** and use *Inflow* = charging, *Outflow* = discharging.

**On the Fronius inverter**, add a secondary meter of type Fronius Smart Meter IP
at your Home Assistant's IP address with Modbus address **241**, and choose the
**external generator** position.

**Check it:** while the battery discharges, Fronius should show it as
generation. If it's the wrong way round, enable **Invert** under
**Configure → Meter power sensor**.

Like a real meter installed with the grid on one side, the meter reports
power flowing *from the grid side into the device* as positive — so battery
charging is positive and discharging (generation) is negative on the wire.
Other positions work the same way: **Consumption path / subload** (positive
sensor = consuming) and **Feed-in point** (positive sensor = importing).

### Sensor sign conventions

These are the values served to the Wattpilot (Fronius Solar API conventions):

| Field | Sign convention | Notes |
|-------|----------------|-------|
| Grid Power | positive = importing, negative = exporting | Grid meter power |
| Solar Generation | positive while producing | Solar panel output |
| Battery Power | positive = discharging, negative = charging | Fronius `P_Akku` |
| House Consumption | negative | Most HA sensors are positive — enable **Invert consumption sign** |
| Battery State of Charge | 0–100% | Battery percentage |

If a sensor has the opposite sign, enable its **Invert** toggle. If your meter or battery reports the two directions as separate positive sensors, use the **Separate … sensors** section of that step instead of the signed sensor (not both).

---

## Upgrading from 1.1

Your settings are migrated automatically. Two behaviour changes to check once:

- **Battery sign fixed.** 1.1 documented and sent battery power as *positive = charging*, but the Fronius API defines `P_Akku` as *positive = discharging* — so the Wattpilot saw a charging battery as discharging and vice versa. Setups using separate charge/discharge sensors are corrected automatically; setups with a single battery sensor have **Invert battery sign** flipped so the sensor keeps its old meaning. Afterwards the *Battery Power* diagnostic sensor should read **positive while discharging** — if it doesn't, toggle **Configure → Battery & house load → Invert battery sign**.
- **Energy counters persist.** Grid import/export and PV energy now continue across restarts (they restarted from 0 before). *Energy Today* now resets at midnight.

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
- **Battery Power** — open **Separate charge/discharge sensors** and map your battery's charge/discharge sensors
- **Battery State of Charge** — your battery's state of charge sensor

For load balancing, map the per-phase sensors from your Fronius Smart Meter:

- `sensor.fronius_current_phase_1` / `_2` / `_3`
- `sensor.fronius_power_factor_phase_1` / `_2` / `_3`
- `sensor.fronius_reactive_power_phase_1` / `_2` / `_3`

You can also enable **Configure → Smart Meter IP** to give the SnapIN a virtual grid meter, and add the battery as a
[virtual smart meter at the external generator position](#virtual-smart-meter--ac-coupled-battery-as-an-external-generator)
so Fronius accounts for it.

### Site with a third-party inverter and no Fronius hardware

You have a non-Fronius inverter (e.g. Growatt, SolarEdge, Enphase) and a separate energy meter. The Wattpilot has no inverter to pair with — this integration provides that.

- **Grid Power Sensor** — your energy meter (e.g. Shelly 3EM; use **Separate import/export sensors** for dual readings)
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

Each virtual inverter exposes diagnostic entities showing exactly what is being served to the Wattpilot:

- `sensor.<name>_grid_power` — Grid Power (W)
- `sensor.<name>_pv_power` — Solar Generation (W)
- `sensor.<name>_battery_power` — Battery Power (W, positive = discharging)
- `sensor.<name>_load_power` — House Consumption (W)
- `sensor.<name>_battery_soc` — Battery State of Charge (%)
- `sensor.<name>_energy_today` — daily PV accumulator (Wh)
- `sensor.<name>_grid_energy_imported` / `_exported` — cumulative grid import/export (Wh) — disabled by default; enable to add to the Energy dashboard
- `sensor.<name>_modbus_address` — Modbus unit ID (when Smart Meter IP is enabled)
- Per-phase power, current, voltage, power factor, and reactive power (when configured)

Each virtual smart meter exposes `sensor.<name>_meter_power` (the value Fronius reads — negative = towards the grid), plus energy imported/exported and its Modbus unit ID (disabled by default).

Sensors for unconfigured fields are hidden automatically.

---

## Known Issues

### "P_Grid is null" error when switching pairing
If the Wattpilot is currently paired with another inverter (e.g. a real Fronius
SnapIN), attempting to pair with the virtual inverter while the old pairing is
still active may show "An error occurred — P_Grid is null".
**Fix:** Fully unpair from the existing inverter first, wait a few seconds,
then pair with the virtual inverter. This is a Wattpilot app limitation, not
an issue with the virtual inverter itself.

*Fixed in 1.2:* enabling a diagnostic sensor or saving options no longer makes
every sensor unavailable until a restart. (Reloading the integration hung while
the Fronius inverter held its Modbus connection open.)

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
- Configure the per-phase sensors (**Configure → Load balancing**). Without them, load balancing falls back to equal phase splitting.
- If you have a Fronius Smart Meter, also map **Power Factor Phase A/B/C** and **Reactive Power Phase A/B/C** — current alone at near-zero real power gives unstable power factor readings

**Fronius doesn't find a virtual smart meter**
- Check the unit ID on the Fronius matches the meter's (see its *Modbus Device Address* diagnostic sensor)
- The HA log shows `Smart Meter IP '<name>' serving on port 502, unit 241` when a meter starts
- Port 502 needs root; Home Assistant OS has it. Elsewhere use a port above 1024 if Fronius lets you set one

**Sensors show unavailable**
- Check the mapped entity IDs exist and have numeric states in Developer Tools → States
- Check HA logs for errors from `fronius_virtual_inverter`

---

## Architecture

```
Home Assistant sensors
        │
        ▼
FroniusVirtualInverterCoordinator   (one per entry; reads sensors every N seconds,
        │                            keeps energy counters in .storage)
        │
        ├── Virtual inverter entry
        │   ├── FroniusSolarAPIServer   (aiohttp HTTP server)
        │   │       ├── GET /solar_api/v1/GetPowerFlowRealtimeData.fcgi  ◄── Wattpilot polls this
        │   │       ├── GET /solar_api/v1/GetMeterRealtimeData.cgi       ◄── Wattpilot load balancing
        │   │       ├── GET /solar_api/v1/GetInverterInfo.fcgi
        │   │       └── GET /solar_api/v1/GetStorageRealtimeData.fcgi
        │   ├── RawMDNSAnnouncer        (raw UDP mDNS multicast, IPv4 + IPv6)
        │   │       ◄── Wattpilot discovers _Fronius-SE-Inverter._tcp.local.
        │   └── SunSpecMeter (optional) — grid meter, unit 240
        │
        └── Virtual smart meter entry
            └── SunSpecMeter — e.g. AC-coupled battery, unit 241
                    │
                    ▼
        ModbusTcpServer  (one per port, routes requests by unit ID)
                ◄── Real Fronius inverter polls its Smart Meter IPs
```

`meter.py` holds the per-phase model (power split, derived current, apparent
power, power factor) shared by the HTTP meter endpoint and the Modbus meters.

---

## Development

```bash
pip install -r requirements_test.txt
pytest
```

The tests use Home Assistant's own test harness to run the config flows,
the 1.1 → 1.2 migration, and real HTTP and Modbus servers on local ports.
CI also runs HACS validation and hassfest.

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
