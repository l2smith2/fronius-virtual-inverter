"""
Fronius Smart Meter IP emulation via SunSpec Modbus TCP.

Emulates a Fronius Smart Meter IP on port 502 (or configurable).
The Fronius GEN24 / Wattpilot will discover this as a primary grid meter
and use the W (real power) register for surplus charging decisions.

Register layout (SunSpec model 213, unit_id=240):
  All numbers are Modbus register numbers (1-based); wire address = register - 1.

  40001-40002  SunS identifier (0x53756e53)
  40003        Common model ID = 1
  40004        Common model length = 65
  40005-40020  Manufacturer: "Fronius"
  40021-40036  Model: "Smart Meter IP"
  40037-40044  Options: "1.0"
  40045-40052  SW Version: "1.0.0"
  40053-40068  Serial number
  40069        Modbus device address = 240
  (no end-of-common-block pad — meter model immediately follows)

  Meter model (SunSpec model 213 = three-phase):
  40070        Model ID = 213
  40071        Length = 124
  40072-40073  A  (total current) float32
  40074-40075  AphA float32
  40076-40077  AphB float32
  40078-40079  AphC float32
  40080-40081  PhV (avg V-N) float32
  40082-40083  PhVphA float32
  40084-40085  PhVphB float32
  40086-40087  PhVphC float32
  40088-40089  PPV (avg V-V) float32
  40090-40091  PhVphAB float32
  40092-40093  PhVphBC float32
  40094-40095  PhVphCA float32
  40096-40097  Hz float32           ← 50.0 Hz
  40098-40099  W  float32           ← TOTAL REAL POWER (key register!)
  40100-40101  WphA float32
  40102-40103  WphB float32
  40104-40105  WphC float32
  40106-40107  VA float32
  40108-40109  VAphA float32
  40110-40111  VAphB float32
  40112-40113  VAphC float32
  40114-40115  VAR float32
  40116-40117  VARphA float32
  40118-40119  VARphB float32
  40120-40121  VARphC float32
  40122-40123  PF float32
  40124-40125  PFphA float32
  40126-40127  PFphB float32
  40128-40129  PFphC float32
  40130-40131  TotWhExp float32     ← total exported energy Wh
  40132-40133  TotWhExpphA float32
  40134-40135  TotWhExpphB float32
  40136-40137  TotWhExpphC float32
  40138-40139  TotWhImp float32     ← total imported energy Wh
  40140-40141  TotWhImpphA float32
  40142-40143  TotWhImpphB float32
  40144-40145  TotWhImpphC float32
  40146-40147  TotVAhExp float32
  40148-40149  TotVAhExpphA float32
  40150-40151  TotVAhExpphB float32
  40152-40153  TotVAhExpphC float32
  40154-40155  TotVAhImp float32
  40156-40157  TotVAhImpphA float32
  40158-40159  TotVAhImpphB float32
  40160-40161  TotVAhImpphC float32
  40162-40163  TotVArhImpQ1 float32
  ...  (VAr quadrant registers, 16 floats, zeroed)
  40192-40193  TotVArhExpQ4PhC float32
  40194-40195  Evt (events) uint32 = 0
  40196        End model ID = 0xFFFF
  40197        End block L = 0x0000

Sign convention: W positive = importing from grid, negative = exporting.
This matches Fronius convention (same as P_Grid in Solar API).
"""
from __future__ import annotations

import asyncio
import logging
import struct
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .coordinator import FroniusVirtualInverterCoordinator

_LOGGER = logging.getLogger(__name__)

# SunSpec constants
SUNSPEC_SID = 0x53756e53  # 'SunS'
SUNSPEC_END = 0xFFFF

# Modbus function codes
FC_READ_HOLDING = 0x03
FC_READ_INPUT = 0x04

# Common block starts at register 40001 (address 40000)
COMMON_BLOCK_START = 40000  # wire address (register - 1)
METER_MODEL_START = 40069   # wire address where meter model ID sits


class FroniusSmartMeterModbusServer:
    """
    Async Modbus TCP server emulating a Fronius Smart Meter IP.

    Implements a raw TCP server (no pymodbus dependency) that handles
    Modbus TCP frames and responds to Read Holding Registers (FC=0x03)
    requests for the SunSpec meter register block.
    """

    def __init__(
        self,
        coordinator: "FroniusVirtualInverterCoordinator",
        port: int,
        serial: str,
        unit_id: int = 240,
    ) -> None:
        self._coordinator = coordinator
        self._port = port
        self._serial = serial
        self._unit_id = unit_id
        self._server: asyncio.AbstractServer | None = None

    async def start(self) -> None:
        """Start the Modbus TCP server."""
        self._server = await asyncio.start_server(
            self._handle_client,
            "0.0.0.0",
            self._port,
        )
        _LOGGER.info(
            "Fronius Smart Meter IP Modbus server started on port %d (unit_id=%d)",
            self._port,
            self._unit_id,
        )

    async def stop(self) -> None:
        """Stop the Modbus TCP server."""
        if self._server:
            self._server.close()
            await self._server.wait_closed()
        _LOGGER.info("Fronius Smart Meter IP Modbus server stopped")

    async def _handle_client(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        """Handle a Modbus TCP client connection."""
        peer = writer.get_extra_info("peername")
        _LOGGER.debug("Modbus client connected: %s", peer)
        try:
            while True:
                # Modbus TCP frame: 6-byte MBAP header + PDU
                header = await reader.readexactly(6)
                if not header or len(header) < 6:
                    break

                transaction_id = (header[0] << 8) | header[1]
                # protocol_id = (header[2] << 8) | header[3]  # always 0
                length = (header[4] << 8) | header[5]

                pdu = await reader.readexactly(length)
                if not pdu or len(pdu) < length:
                    break

                unit_id = pdu[0]
                func_code = pdu[1]

                # Only respond to our unit ID
                if unit_id != self._unit_id:
                    _LOGGER.debug(
                        "Ignoring request for unit_id=%d (ours=%d)",
                        unit_id, self._unit_id,
                    )
                    continue

                if func_code in (FC_READ_HOLDING, FC_READ_INPUT):
                    if len(pdu) < 6:
                        continue
                    start_addr = (pdu[2] << 8) | pdu[3]
                    count = (pdu[4] << 8) | pdu[5]

                    _LOGGER.debug(
                        "Modbus read FC=%02x start=%d count=%d",
                        func_code, start_addr, count,
                    )

                    try:
                        response_data = self._read_registers(start_addr, count)
                    except Exception as e:
                        _LOGGER.error("Error building Modbus register map: %s", e)
                        exc_pdu = bytes([unit_id, func_code | 0x80, 0x04])
                        writer.write(self._mbap(transaction_id, exc_pdu))
                        await writer.drain()
                        continue

                    if response_data is None:
                        # Exception response: illegal data address
                        exc_pdu = bytes([unit_id, func_code | 0x80, 0x02])
                        resp = self._mbap(transaction_id, exc_pdu)
                    else:
                        byte_count = len(response_data)
                        resp_pdu = bytes([unit_id, func_code, byte_count]) + response_data
                        resp = self._mbap(transaction_id, resp_pdu)

                    writer.write(resp)
                    await writer.drain()
                else:
                    # Unsupported function code
                    exc_pdu = bytes([unit_id, func_code | 0x80, 0x01])
                    writer.write(self._mbap(transaction_id, exc_pdu))
                    await writer.drain()

        except (asyncio.IncompleteReadError, ConnectionResetError):
            pass
        except Exception as e:
            _LOGGER.debug("Modbus client error: %s", e)
        finally:
            writer.close()
            _LOGGER.debug("Modbus client disconnected: %s", peer)

    def _mbap(self, transaction_id: int, pdu: bytes) -> bytes:
        """Build a Modbus TCP MBAP header around a PDU."""
        return struct.pack(">HHH", transaction_id, 0, len(pdu)) + pdu

    def _read_registers(self, start_addr: int, count: int) -> bytes | None:
        """
        Build the register response for a read holding registers request.
        Returns raw bytes (2 bytes per register) or None on error.
        """
        registers = self._build_register_map()
        result = bytearray()

        for addr in range(start_addr, start_addr + count):
            if addr not in registers:
                # Return 0x0000 for unmapped registers (many are don't-care)
                result += b"\x00\x00"
            else:
                result += registers[addr]

        return bytes(result)

    def _build_register_map(self) -> dict[int, bytes]:
        """Build the complete SunSpec register map as {wire_address: 2_bytes}."""
        data = self._coordinator.data or {}
        p_grid = data.get("P_Grid") or 0.0

        # Accumulated energy split (simplified: assume 50/50 split if only net known)
        # Positive P_Grid = import, negative = export
        tot_wh_imp = data.get("_tot_wh_imp") or 0.0
        tot_wh_exp = data.get("_tot_wh_exp") or 0.0

        regs: dict[int, bytes] = {}

        def set_float(addr: int, value: float) -> None:
            raw = struct.pack(">f", float(value))
            regs[addr] = raw[0:2]
            regs[addr + 1] = raw[2:4]

        def set_uint16(addr: int, value: int) -> None:
            regs[addr] = struct.pack(">H", value & 0xFFFF)

        def set_uint32(addr: int, value: int) -> None:
            raw = struct.pack(">I", value & 0xFFFFFFFF)
            regs[addr] = raw[0:2]
            regs[addr + 1] = raw[2:4]

        def set_string(addr: int, text: str, num_regs: int) -> None:
            encoded = text.encode("ascii")
            padded = encoded[:num_regs * 2].ljust(num_regs * 2, b"\x00")
            for i in range(num_regs):
                regs[addr + i] = padded[i * 2: i * 2 + 2]

        # ── Common block ──────────────────────────────────────────────────
        # Register 40001 = wire addr 40000
        # SunS identifier (uint32 across 40000-40001)
        set_uint32(40000, SUNSPEC_SID)          # 40001-40002
        set_uint16(40002, 1)                     # 40003 ID=1 (Common model)
        set_uint16(40003, 65)                    # 40004 L=65 registers

        set_string(40004, "Fronius", 16)         # 40005-40020 Mn
        set_string(40020, "Smart Meter IP", 16)  # 40021-40036 Md
        set_string(40036, "1.0", 8)              # 40037-40044 Opt
        set_string(40044, "1.0.0", 8)            # 40045-40052 Vr
        set_string(40052, self._serial, 16)      # 40053-40068 SN
        set_uint16(40068, self._unit_id)          # 40069 DA

        # ── Meter model 213 (three-phase float) ───────────────────────────
        # Starts at wire addr 40069 (register 40070)
        set_uint16(40069, 213)    # Model ID 213
        set_uint16(40070, 124)    # Length = 124 registers

        # Currents (A) — use NaN / 0 since we don't have per-phase current
        per_phase_i = p_grid / 3 / 230.0 if p_grid != 0 else 0.0
        set_float(40071, per_phase_i * 3)   # A total
        set_float(40073, per_phase_i)        # AphA
        set_float(40075, per_phase_i)        # AphB
        set_float(40077, per_phase_i)        # AphC

        # Voltages (V)
        set_float(40079, 230.0)   # PhV avg
        set_float(40081, 230.0)   # PhVphA
        set_float(40083, 230.0)   # PhVphB
        set_float(40085, 230.0)   # PhVphC
        set_float(40087, 400.0)   # PPV avg (line-to-line)
        set_float(40089, 400.0)   # PhVphAB
        set_float(40091, 400.0)   # PhVphBC
        set_float(40093, 400.0)   # PhVphCA

        # Frequency (float32): reg 40096-40097 = wire 40095-40096
        set_float(40095, 50.0)    # Hz

        # ── THE KEY REGISTER: W = total real power ────────────────────────
        # reg 40098-40099 = wire 40097-40098; positive = importing, negative = exporting
        set_float(40097, p_grid)       # W
        set_float(40099, p_grid / 3)   # WphA
        set_float(40101, p_grid / 3)   # WphB
        set_float(40103, p_grid / 3)   # WphC

        # VA (apparent power): reg 40106-40107 = wire 40105-40106
        set_float(40105, abs(p_grid))       # VA
        set_float(40107, abs(p_grid) / 3)   # VAphA
        set_float(40109, abs(p_grid) / 3)   # VAphB
        set_float(40111, abs(p_grid) / 3)   # VAphC

        # VAR (reactive power — zero): reg 40114-40115 = wire 40113-40114
        set_float(40113, 0.0)   # VAR
        set_float(40115, 0.0)   # VARphA
        set_float(40117, 0.0)   # VARphB
        set_float(40119, 0.0)   # VARphC

        # Power factor: reg 40122-40123 = wire 40121-40122
        set_float(40121, 1.0)   # PF
        set_float(40123, 1.0)   # PFphA
        set_float(40125, 1.0)   # PFphB
        set_float(40127, 1.0)   # PFphC

        # Energy registers (Wh): TotWhExp at reg 40130-40131 = wire 40129-40130
        set_float(40129, tot_wh_exp)        # TotWhExp
        set_float(40131, tot_wh_exp / 3)    # TotWhExpPhA
        set_float(40133, tot_wh_exp / 3)    # TotWhExpPhB
        set_float(40135, tot_wh_exp / 3)    # TotWhExpPhC

        # TotWhImp at reg 40138-40139 = wire 40137-40138
        set_float(40137, tot_wh_imp)        # TotWhImp
        set_float(40139, tot_wh_imp / 3)    # TotWhImpPhA
        set_float(40141, tot_wh_imp / 3)    # TotWhImpPhB
        set_float(40143, tot_wh_imp / 3)    # TotWhImpPhC

        # VAh export/import (zero) — 8 floats, reg 40146-40161 = wire 40145-40160
        for addr in range(40145, 40161, 2):
            set_float(addr, 0.0)

        # VAr quadrant registers (zero) — 16 floats, reg 40162-40193 = wire 40161-40192
        for addr in range(40161, 40193, 2):
            set_float(addr, 0.0)

        # Events uint32 = 0: reg 40194-40195 = wire 40193-40194
        set_uint32(40193, 0)

        # End block: reg 40196 = 0xFFFF (wire 40195), reg 40197 = 0x0000 (wire 40196)
        set_uint16(40195, SUNSPEC_END)
        set_uint16(40196, 0)

        return regs
