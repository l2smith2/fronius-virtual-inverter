# Fronius Virtual Inverter — Project Context

## What this integration does
Emulates a Fronius GEN24 inverter + Fronius Smart Meter IP on the local network so a Fronius Wattpilot EV charger can perform PV surplus (Eco) charging without real Fronius hardware. Reads power flow data from HA sensors and serves it via two protocols.

## Two emulation modes
1. **HTTP Solar API v1** (port 80) — impersonates a Fronius Datamanager 2.0 inverter
   - Endpoints: GetAPIVersion.cgi, GetPowerFlowRealtimeData.fcgi, GetLoggerInfo.fcgi, GetInverterInfo.fcgi, GetMeterRealtimeData.fcgi, GetStorageRealtimeData.fcgi, GetActiveDeviceInfo.cgi
   - DT=102, CompatibilityRange=1.8-1
   - GetLoggerInfo returns UniqueID="240.{system_name}" and Systemname
   - GetInverterInfo returns CustomName=system_name, UniqueID=serial, MaxACCurrent=ct_rating
   - GetMeterRealtimeData returns per-phase power and current (PowerReal_P_Phase_1/2/3, Current_AC_Phase_1/2/3)
   - GetActiveDeviceInfo responds to ?DeviceClass=Meter with address 0, DT=-1

2. **Modbus TCP Smart Meter IP** (port 502) — emulates Fronius Smart Meter IP
   - SunSpec float model 213 (three-phase)
   - Unit ID = 240
   - Hz is uint16 at wire address 40095 (register 40096), value 5000 = 50.00Hz
   - W register at wire address 40097 (registers 40098-40099) — confirmed by live test
   - Successfully detected by real Fronius SnapIN at 192.168.2.79
   - SnapIN adds it as TCP meter at 192.168.2.153:502, unit ID 240
   - Data appears in SolarWeb ✓

## mDNS discovery — WORKING ✓

The Wattpilot scans for exactly two mDNS service types (confirmed by pcap):
- `_Fronius-SE-Inverter._tcp.local.`
- `_Fronius-SE-SmartMeter._tcp.local.`

Both exceed zeroconf library's 15-byte label limit so we can't use ServiceInfo.
`RawMDNSAnnouncer` in `mdns_announcer.py` sends raw UDP multicast directly.

**Key fixes that solved mDNS pairing:**
1. **Bind to port 5353 with SO_REUSEPORT** — RFC 6762 requires mDNS responses to originate from UDP source port 5353. Wattpilot was silently discarding our responses because they came from ephemeral ports. SO_REUSEPORT allows sharing port 5353 with HA's zeroconf daemon.
2. **IPv6 support with AAAA records** — Wattpilot queries from both IPv4 (192.168.2.225) and IPv6 link-local (fe80::c249:efff:fe1e:5188). Added second socket sending to `ff02::fb` with correct interface scope ID, and AAAA records in the additional section.

**Confirmed facts about Wattpilot mDNS behaviour:**
- Sends queries from **both** IPv4 and IPv6 link-local — both must be answered
- IPv6 multicast requires a scope ID: interface index passed as 4-tuple scope_id in Python sendto
- Packet size must be kept under 400 bytes — full DeviceMeta JSON grew packets to 730 bytes; stripped to essential fields only
- `cci` WebSocket property holds the paired inverter: `{ip, label, commonName, paired, reachableMdns, reachableUdp, reachableHttp}` — **read-only**, cannot be written via WebSocket
- SnapIN (192.168.2.79) sends **zero** mDNS traffic once paired — goes completely silent after pairing

**Result:** Wattpilot discovers, pairs, and uses the virtual inverter for PV surplus (Eco) charging. ✓

## Display name / serial number
- `system_name` (configured in setup) is used as the serial — so UniqueID becomes `240.<system_name>` (e.g. `240.Tesla`)
- This makes the Wattpilot pairing screen show `Tesla (192.168.2.153)` instead of a hex hash
- `GetInverterInfo.CustomName` also uses `system_name`
- `GetLoggerInfo.UniqueID` uses `240.<system_name>`
- mDNS TXT records include `CommonName=pilot-0.5e-<system_name>`, `UniqueID=240.<system_name>`, `Systemname=<system_name>`
- Falls back to 8-char MD5 hex hash of entry_id if system_name is not set

## Per-phase load balancing
- `grid_phases` config: "1" (single-phase) or "3" (three-phase), default single
- `grid_ct_rating`: circuit breaker amps, default 32A — reported as `MaxACCurrent` in GetInverterInfo
- Optional per-phase power sensors: `p_grid_phase_a/b/c` (W)
- Optional per-phase current sensors: `i_grid_phase_a/b/c` (A) — alternative to power
- Optional per-phase voltage sensors: `v_grid_phase_a/b/c` (V) — defaults to 240V if not set
- Optional per-phase power factor sensors: `power_factor_phase_a/b/c` — derived from P/(I×V) if not set
- Optional per-phase reactive power sensors: `q_grid_phase_a/b/c` (VAr) — defaults to 0 if not set
- If per-phase sensors not configured: auto-splits total P_Grid equally across phases (or all on phase 1 for single-phase)
- If current sensors not provided: derives from P/V (240V default)
- CT rating and per-phase current can also be configured directly in the Solar.wattpilot app

**Load balancing stability note:**
- Current sensor alone causes inconsistency at near-zero real power (high I, low P → PF≈-0.02)
- Solution: configure Power Factor and Reactive Power Phase sensors from Fronius Smart Meter integration
- These are available from the real SnapIN integration entities (see Fronius Smart Meter sensors below)

**Fronius Smart Meter sensors available (from real SnapIN integration):**
- `sensor.fronius_current_phase_1` (A)
- `sensor.fronius_power_factor_phase_1`
- `sensor.fronius_reactive_power_phase_1` (VAr)
- `sensor.fronius_voltage_phase_1` (V)
- `sensor.fronius_real_power` (W)
- `sensor.fronius_frequency_phase_average` (Hz)

## GetMeterRealtimeData response format
- `.cgi` (Device scope, Wattpilot polls this) and `.fcgi` (System scope) both handled
- Response matches real Fronius SnapIN format: `TimeStamp`, `Frequency_Phase_Average`, `Voltage_AC_Phase_1/2/3`, `PowerApparent_S_*`, `PowerFactor_*`, `PowerReactive_Q_*`, `EnergyReal_WAC_*`
- `PowerApparent_S = sqrt(P² + Q²)` when Q≠0, else `abs(P)`
- `PowerFactor`: from sensor → derived from P/(I×V) → sign-based fallback (1.0 import, -1.0 export)
- Energy accumulators (`EnergyReal_WAC_*`) tracked in coordinator as running totals
- For single-phase: only Phase_1 fields included; for three-phase: Phase_1/2/3 all included

## Confirmed working ✓
- Wattpilot discovery and pairing via mDNS ✓
- PV surplus (Eco) charging active ✓
- HTTP Solar API serving live data on port 80 ✓
- Modbus Smart Meter IP on port 502 — polled by SnapIN every second ✓
- SolarWeb shows virtual meter data ✓
- fronius-virtual.local resolves via _http._tcp mDNS ✓
- Sensor unit auto-conversion: kW→W, kWh→Wh, MW→W, MWh→Wh ✓
- Per-phase data in GetMeterRealtimeData for load balancing ✓
- system_name used as serial for human-readable display name ✓
- GetMeterRealtimeData.cgi (Device scope) served correctly — what Wattpilot polls ✓
- Per-phase voltage, power factor, reactive power sensors supported ✓
- Config flow restructured into 4 steps: user → grid → generation → advanced ✓

## Network topology
- HA host: 192.168.2.153 (Proxmox VM)
- Wattpilot: 192.168.2.225 (Golden_Duck_91017579, firmware 42.5)
- Real SnapIN inverter: 192.168.2.79 (Fronius Datamanager 2.0, DT=102, name: Smith, serial: 240.1248152)
- Proxmox host: separate machine, vmbr0 bridge, multicast snooping disabled

## Sign conventions (Fronius)
- P_Grid: positive = import, negative = export
- P_Akku: positive = charging, negative = discharging
- P_PV: always positive
- P_Load: always negative

## GitHub
https://github.com/l2smith2/fronius-virtual-inverter

## HA path
/config/custom_components/fronius_virtual_inverter/
