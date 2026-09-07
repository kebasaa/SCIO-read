"""Safe, read-only probing of the SCiO's undocumented USB command surface.

The decompiled apps expose no command that reads firmware or memory out of the
device. Three opcodes are *declared* by the firmware but never sent by any app,
so their behaviour is unknown: READ_EVENT_LOG (0x06), PARAMETER_GET (0x08),
BIST (0x09). The file-list handler also reserves the id band 87-95, leaving a
few unclaimed opcodes. This module probes exactly that surface, and nothing
else, to see whether any of it returns useful data (a memory region, a
parameter, a log, or - the jackpot - a file body).

Safety is the whole point of this module:

* It sends ONLY opcodes on an explicit allowlist. Write / state-changing
  opcodes (PARAMETER_SET, FILE_DOWNLOAD, RESET_DEVICE, WRITE_USER_DEVICE_NAME,
  WRITE_BLE, READY_FOR_WR, CLEAR_READY_FOR_WR, SET_INDICATION_LED) are refused.
* Payloads are empty by default; the only non-empty payloads are a file id (for
  the extended file-header probe) and small parameter ids - both non-mutating.
* The reserved-band opcodes are gated behind an explicit ``enable_reserved``
  flag and sent one at a time.
* Every request/response is logged verbatim to ``01_rawdata/probe_logs/`` so a
  failed hypothesis is still a durable record.
"""

from __future__ import annotations

import json
import struct
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

from . import protocol
from .protocol import Cmd
from .usb import ScioProtocolError, ScioTimeout, ScioUSB

PROBE_LOG_DIR = Path(__file__).resolve().parent.parent / "01_rawdata" / "probe_logs"

# Opcodes that are safe to *send* from this module. Everything here is a read /
# query / self-test; none writes, resets, renames, or downloads.
SAFE_READS = {
    Cmd.READ_DEVICE_STATUS: "READ_DEVICE_STATUS(0x00)",
    Cmd.READ_DEVICE_ID: "READ_DEVICE_ID(0x01)",
    Cmd.READ_TEMPERATURE: "READ_TEMPERATURE(0x04)",
    Cmd.READ_BATTERY_STATE: "READ_BATTERY_STATE(0x05)",
    Cmd.READ_EVENT_LOG: "READ_EVENT_LOG(0x06)",     # declared, never used by app
    Cmd.PARAMETER_GET: "PARAMETER_GET(0x08)",       # declared, never used by app
    Cmd.BIST: "BIST(0x09)",                         # declared, never used by app
    Cmd.READ_BLE_ID: "READ_BLE_ID(0x84)",
    Cmd.READ_BLE_STATUS: "READ_BLE_STATUS(0x85)",
    Cmd.READ_FILE_HEADER: "READ_FILE_HEADER(0x87)",
    Cmd.READ_FILE_LIST: "READ_FILE_LIST(0x94)",
    Cmd.READ_BLE: "READ_BLE(0x9B)",
}

# Unclaimed opcodes inside the file-list reserved band 87-95 (0x57..0x5F). The
# app uses 0x87 (header) and 0x94 (list); these are the gaps worth a blind read.
RESERVED_BAND = [0x88, 0x89, 0x8A, 0x8B, 0x8C, 0x8D, 0x8E, 0x8F, 0x93, 0x95]

# Never send these, ever, from the probe.
FORBIDDEN = protocol.WRITE_COMMANDS


@dataclass
class ProbeResult:
    timestamp: str
    label: str
    command: int
    payload_hex: str
    request_hex: str
    ok: bool
    response_command: int | None = None
    response_len: int | None = None
    response_hex: str = ""
    response_ascii: str = ""
    response_u32le: list | None = None
    elapsed_s: float = 0.0
    note: str = ""


def _ascii(data: bytes) -> str:
    return "".join(chr(b) if 32 <= b <= 126 else "." for b in data)


def _u32le(data: bytes, limit: int = 64) -> list:
    n = min(len(data) // 4, limit)
    return list(struct.unpack_from("<%dI" % n, data)) if n else []


class ScioProbe:
    """Wraps a :class:`ScioUSB` session and sends only allowlisted read probes."""

    def __init__(self, dev: ScioUSB, log_dir: Path | str = PROBE_LOG_DIR,
                 max_response: int = 65535):
        self.dev = dev
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.max_response = max_response
        self.results: list[ProbeResult] = []

    # -- core ------------------------------------------------------------
    def probe(self, cmd: int, payload: bytes = b"", label: str = "",
              allow_reserved: bool = False) -> ProbeResult:
        """Send one allowlisted read opcode and capture the response."""
        if cmd in FORBIDDEN:
            raise PermissionError(f"refusing to send write/state opcode 0x{cmd:02X}")
        if cmd not in SAFE_READS and not (allow_reserved and cmd in RESERVED_BAND):
            raise PermissionError(
                f"opcode 0x{cmd:02X} is not on the probe allowlist "
                f"(set allow_reserved=True only for the reserved band {[hex(x) for x in RESERVED_BAND]})"
            )
        label = label or SAFE_READS.get(cmd, f"opcode(0x{cmd:02X})")
        frame = protocol.build_command(cmd, payload, seq=self.dev._next_seq())
        t0 = time.time()
        res = ProbeResult(
            timestamp=datetime.now().isoformat(timespec="seconds"),
            label=label, command=cmd, payload_hex=payload.hex(),
            request_hex=frame.hex(), ok=False,
        )
        try:
            self.dev.ser.reset_input_buffer()
            self.dev.ser.write(frame)
            self.dev.ser.flush()
            resp = self.dev._read_response()
            data = resp.data
            res.ok = True
            res.response_command = resp.command
            res.response_len = resp.length
            res.response_hex = data[:512].hex()
            res.response_ascii = _ascii(data[:512])
            res.response_u32le = _u32le(data)
            if resp.length > self.max_response:
                res.note = "response length exceeds guard; stream may be desynced"
        except ScioTimeout:
            res.note = "timeout (no response)"
        except ScioProtocolError as e:
            res.note = f"protocol error: {e}"
        res.elapsed_s = round(time.time() - t0, 3)
        self.results.append(res)
        self._log(res)
        time.sleep(self.dev.SLEEP_BETWEEN_COMMANDS)
        return res

    def _log(self, res: ProbeResult):
        path = self.log_dir / f"{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}_cmd{res.command:02X}.json"
        path.write_text(json.dumps(asdict(res), indent=1), encoding="utf-8")

    # -- targeted probes -------------------------------------------------
    def probe_event_log(self) -> ProbeResult:
        return self.probe(Cmd.READ_EVENT_LOG, label="READ_EVENT_LOG(0x06)")

    def probe_bist(self) -> ProbeResult:
        # A self-test may take longer to answer; the transport timeout covers it.
        return self.probe(Cmd.BIST, label="BIST(0x09)")

    def probe_device_status(self) -> ProbeResult:
        return self.probe(Cmd.READ_DEVICE_STATUS, label="READ_DEVICE_STATUS(0x00)")

    def probe_parameter_get(self, ids=None, shapes=("<I", "<H", "")) -> list[ProbeResult]:
        """Try PARAMETER_GET (0x08) with various parameter ids / payload shapes."""
        if ids is None:
            ids = list(range(0, 33)) + [89, 90, 91, 92, 100, 101, 102, 103]
        out = []
        for pid in ids:
            for shape in shapes:
                payload = struct.pack(shape, pid) if shape else b""
                out.append(self.probe(Cmd.PARAMETER_GET, payload,
                                      label=f"PARAMETER_GET(0x08) id={pid} shape={shape or 'empty'}"))
        return out

    def probe_file_header_extended(self, file_id: int) -> list[ProbeResult]:
        """READ_FILE_HEADER with offset/length appended, to test for a body read.

        The app only sends a bare u32 file id. If the firmware honours extra
        (offset, length) words and returns more than the 16-byte header, that is
        a path to stream the file body out - the one real USB win condition.
        """
        variants = [
            ("id_only", struct.pack("<I", file_id)),
            ("id_off0_len16", struct.pack("<III", file_id, 0, 16)),
            ("id_off0_len256", struct.pack("<III", file_id, 0, 256)),
            ("id_off16_len256", struct.pack("<III", file_id, 16, 256)),
        ]
        out = []
        for name, payload in variants:
            out.append(self.probe(Cmd.READ_FILE_HEADER, payload,
                                  label=f"READ_FILE_HEADER(0x87) file={file_id} {name}"))
        return out

    def probe_reserved_band(self, opcodes=None) -> list[ProbeResult]:
        """Blind read of unclaimed opcodes in the 87-95 band (opt-in)."""
        out = []
        for cmd in (opcodes or RESERVED_BAND):
            out.append(self.probe(cmd, label=f"reserved(0x{cmd:02X})", allow_reserved=True))
        return out

    # -- runner ----------------------------------------------------------
    def run_safe_sweep(self, include_parameter_get: bool = True,
                       include_file_header_ext: bool = True) -> list[ProbeResult]:
        """Walk the safe surface once. Does NOT touch the reserved band."""
        self.probe_device_status()
        self.probe_event_log()
        self.probe_bist()
        if include_parameter_get:
            self.probe_parameter_get(ids=[0, 1, 2, 8, 89, 92, 100, 101, 102, 103])
        if include_file_header_ext:
            for fid in (92, 101, 102, 103):  # dsp_op and the tables
                self.probe_file_header_extended(fid)
        return list(self.results)


def summarize(results: list[ProbeResult]) -> list[dict]:
    """One row per probe that returned data, sorted by response length."""
    rows = []
    for r in results:
        if r.ok and (r.response_len or 0) > 0:
            rows.append({
                "label": r.label,
                "resp_cmd": r.response_command,
                "len": r.response_len,
                "elapsed_s": r.elapsed_s,
                "hex_head": r.response_hex[:48],
                "note": r.note,
            })
    rows.sort(key=lambda d: -(d["len"] or 0))
    return rows
