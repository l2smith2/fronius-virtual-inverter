# Fronius Virtual Inverter — Project Context

## What this integration does
Emulates a Fronius GEN24 inverter + Fronius Smart Meter IP on the local network so a Fronius Wattpilot EV charger can perform PV surplus (Eco) charging without real Fronius hardware. Reads power flow data from HA sensors and serves it via two protocols.

## Two emulation modes
1. **HTTP Solar API v1** (port 80) — impersonates a Fronius Datamanager 2.0 inverter
   - Endpoints: GetAPIVersion.cgi, GetPowerFlowRealtimeData.fcgi, GetLoggerInfo.fcgi
   - DT=102, CompatibilityRange=1.8-1
   - GetLoggerInfo returns UniqueID="240.{serial}" and Systemname

2. **Modbus TCP Smart Meter IP** (port 502) — emulates Fronius Smart Meter IP
   - SunSpec float model 213 (three-phase)
   - Unit ID = 240
   - Hz is uint16 at wire address 40095 (register 40096), value 5000 = 50.00Hz
   - W register at wire address 40097 (registers 40098-40099) — confirmed by live test
   - Successfully detected by real Fronius SnapIN at 192.168.2.79
   - SnapIN adds it as TCP meter at 192.168.2.153:502, unit ID 240
   - Data appears in SolarWeb

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
- SnapIN actively polls our virtual Smart Meter on port 502 every second ✓
- SnapIN actively polls our HTTP Solar API on port 80 ✓
- `ido` WebSocket property can push inverter data directly to Wattpilot but requires sudo/privileged auth (separate issue)

**Result:** Wattpilot now discovers, pairs, and uses the virtual inverter for PV surplus (Eco) charging. ✓

## Remaining known issues
- **Load Balancing shows "not available"** — Wattpilot needs per-phase load data (L1/L2/L3 W) which the current API responses do not provide
- **Device display name** — comes from `Systemname` field in `GetLoggerInfo` response; configurable in integration setup via the System Name option

## Network topology
- HA host: 192.168.2.153 (Proxmox VM)
- Wattpilot: 192.168.2.225 (Golden_Duck_91017579, firmware 42.5)
- Real SnapIN inverter: 192.168.2.79 (Fronius Datamanager 2.0, DT=102)
- Proxmox host: separate machine, vmbr0 bridge, multicast snooping disabled

## Key confirmed facts
- Wattpilot does NOT subnet scan — purely mDNS PTR queries
- Wattpilot paired with SnapIN (Smith, serial 240.1248152) in normal use; can be unpaired for testing
- Virtual Smart Meter successfully added to SnapIN and visible in SolarWeb ✓
- HTTP Solar API serving live data correctly on port 80 ✓
- fronius-virtual.local resolves correctly via _http._tcp mDNS ✓
- Full PV surplus (Eco) charging via virtual inverter working ✓
- Sensor unit auto-conversion (kW→W, kWh→Wh, MW→W, MWh→Wh) in sensor_reader.py ✓

## Sign conventions (Fronius)
- P_Grid: positive = import, negative = export
- P_Akku: positive = charging, negative = discharging
- P_PV: always positive
- P_Load: always negative

## GitHub
https://github.com/l2smith2/fronius-virtual-inverter

## HA path
/config/custom_components/fronius_virtual_inverter/
