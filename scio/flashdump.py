"""Carve SCIO firmware/table candidates from an external-flash dump.

The live unit exposes file metadata but no body-read command.  This module is
for dumps acquired separately (SPI programmer or JTAG).  It prioritizes exact
16-byte metadata headers and treats a matching byte-sum alone as weak evidence.
"""

from __future__ import annotations

import hashlib
import math
import struct
from pathlib import Path

from .paths import portable_path

import numpy as np

from . import firmware

UNIT_HEADERS = {
    "ble_runtime": (87, 119233, 125, 12925168),
    "dsp_boot": (90, 7284, 17, 688456),
    "dsp_dec": (91, 14600, 12, 1548938),
    "dsp_op": (92, 32628, 147, 4151168),
    "unknown_99": (99, 32, 0, 0),
    "deadPixelsIndices": (100, 1714, 3, 97267),
    "centers": (101, 96, 3, 6080),
    "bins": (102, 140, 3, 13587),
    "nPixelsPerBin": (103, 1166, 3, 36371),
}


def digest(data: bytes) -> dict:
    return {"size": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def byte_sum(data: bytes) -> int:
    """Candidate checksum suggested by the magnitude of live header values."""
    return int(np.frombuffer(data, dtype=np.uint8).sum(dtype=np.uint64))


def _all_offsets(data: bytes, needle: bytes, limit=10000):
    out, start = [], 0
    while len(out) < limit:
        pos = data.find(needle, start)
        if pos < 0:
            break
        out.append(pos); start = pos + 1
    return out


def _rolling_sum_offsets(data: bytes, size: int, wanted: int, limit=200):
    if size <= 0 or size > len(data):
        return []
    a = np.frombuffer(data, dtype=np.uint8).astype(np.uint64)
    cs = np.concatenate((np.zeros(1, dtype=np.uint64), np.cumsum(a, dtype=np.uint64)))
    sums = cs[size:] - cs[:-size]
    return np.flatnonzero(sums == wanted)[:limit].astype(int).tolist()


def _entropy(data: bytes) -> float:
    return firmware.entropy(data)


def candidates_for_file(data: bytes, name: str, header: tuple, rolling=True) -> dict:
    file_id, size, version, checksum = header
    packed = struct.pack("<IIII", file_id, size, version, checksum)
    header_offsets = _all_offsets(data, packed)
    rows, seen = [], set()

    def add(offset, source, header_offset=None):
        if offset in seen or offset < 0 or offset + size > len(data):
            return
        seen.add(offset)
        body = data[offset:offset + size]
        calc = byte_sum(body)
        triage = firmware.triage_blob(name, body)
        rows.append({"offset": offset, "offset_hex": f"0x{offset:X}", "source": source,
                     "header_offset": header_offset, "byte_sum": calc,
                     "byte_sum_matches_header": calc == checksum,
                     "sha256": hashlib.sha256(body).hexdigest(), "entropy": round(_entropy(body), 4),
                     "valid_ldr": triage["valid_ldr"], "verdict": triage["verdict"]})

    for h in header_offsets:
        for off in (h + 16, (h + 31) & ~15, (h + 255) & ~255):
            add(off, "exact_metadata_header", h)
    # The Android cache prepended the little-endian checksum to each body.
    for p in _all_offsets(data, struct.pack("<I", checksum), limit=2000):
        add(p + 4, "checksum_prefix", p)
    if rolling and checksum:
        for off in _rolling_sum_offsets(data, size, checksum):
            add(off, "rolling_byte_sum")

    rank = {"exact_metadata_header": 3, "checksum_prefix": 2, "rolling_byte_sum": 1}
    rows.sort(key=lambda r: (r["byte_sum_matches_header"], rank[r["source"]], r["valid_ldr"]), reverse=True)
    for row in rows:
        row["confidence"] = ("strong" if row["source"] == "exact_metadata_header" and row["byte_sum_matches_header"]
                             else "medium" if row["source"] == "checksum_prefix" and row["byte_sum_matches_header"]
                             else "weak")
    return {"name": name, "file_id": file_id, "expected_size": size, "version": version,
            "header_checksum": checksum, "exact_header_offsets": header_offsets,
            "candidates": rows, "candidate_count": len(rows)}


def analyze_dump(path, rolling=True) -> dict:
    path = Path(path); data = path.read_bytes()
    files = {name: candidates_for_file(data, name, header, rolling)
             for name, header in UNIT_HEADERS.items()}
    return {"schema": "scio-flash-dump/1", "path": portable_path(path), **digest(data),
            "entropy": round(_entropy(data), 4), "files": files,
            "strong_candidates": sum(r["confidence"] == "strong" for f in files.values() for r in f["candidates"]),
            "warning": "A byte-sum-only match is weak and must not be treated as recovered firmware."}


def compare_dumps(paths) -> dict:
    blobs = [Path(p).read_bytes() for p in paths]
    base = blobs[0] if blobs else b""
    return {"count": len(blobs), "identical": bool(blobs) and all(x == base for x in blobs[1:]),
            "digests": [digest(x) for x in blobs],
            "different_bytes_from_first": [sum(a != b for a, b in zip(base, x)) + abs(len(base)-len(x))
                                             for x in blobs]}


def extract_strong(report: dict, dump_path, out_dir) -> list[str]:
    """Extract only checksum-confirmed bodies adjacent to an exact metadata header."""
    data, out, written = Path(dump_path).read_bytes(), Path(out_dir), []
    out.mkdir(parents=True, exist_ok=True)
    for name, rec in report["files"].items():
        matches = [r for r in rec["candidates"] if r["confidence"] == "strong"]
        if len(matches) == 1:
            row = matches[0]; body = data[row["offset"]:row["offset"] + rec["expected_size"]]
            target = out / f"{name}.bin"; target.write_bytes(body); written.append(str(target))
    return written
