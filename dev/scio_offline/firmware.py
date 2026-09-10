"""Obtaining and triaging possible SCIO firmware/calibration artifacts.

The (now closed) Consumer Physics server sent eight files to the phone, which
pushed them into the SCiO: ``ble``, ``dsp_boot``, ``dsp_dec``, ``dsp_op`` and
the per-device image-to-spectrum
tables ``deadPixelsIndices``, ``centers``, ``bins``, ``nPixelsPerBin``.

Both the consumer app and the Lab app cached them in Android SharedPreferences:
a string-set ``<user>.firmware.file.names`` plus one
``<string name="dsp_op">base64...</string>`` per file under the *bare* enum
name.  Clearing the set does not delete the strings, so an old phone (or an
``adb backup``) may still hold them.  Every value is base64 of
``[4-byte little-endian checksum][file body]`` (FirmwareUpgradeModel.java).

This module extracts those blobs (SharedPreferences XML, adb ``.ab`` backup,
or loose files), verifies the checksum prefix against the device's own
``READ_FILE_HEADER`` word, and triages each blob (entropy, strings, Blackfin
LDR boot-stream structure) to decide whether ``dsp_op`` is analysable.
"""

from __future__ import annotations

import base64
import io
import json
import math
import re
import struct
import tarfile
import zlib
from collections import Counter
from pathlib import Path
from xml.etree import ElementTree as ET

from scio.protocol import FIRMWARE_FILES

ENUM_NAMES = tuple(n for n in FIRMWARE_FILES if n != "no_file")
FILE_NAMES_KEY = "firmware.file.names"


# --------------------------------------------------------------------------
# Sources
# --------------------------------------------------------------------------

def parse_shared_prefs_xml(path) -> dict:
    """Return ``{enum_name: base64_string}`` found in one SharedPreferences XML."""
    found = {}
    try:
        root = ET.parse(str(path)).getroot()
    except ET.ParseError:
        return found
    for el in root.iter("string"):
        name = el.get("name", "")
        if name in ENUM_NAMES and el.text:
            found[name] = "".join(el.text.split())
    return found


def scan_shared_prefs_dir(directory) -> dict:
    """Harvest firmware blobs from every ``*.xml`` under ``directory`` (recursive)."""
    found = {}
    for p in sorted(Path(directory).rglob("*.xml")):
        for k, v in parse_shared_prefs_xml(p).items():
            found.setdefault(k, {"b64": v, "source": str(p)})
    return found


def extract_adb_backup(ab_path, out_dir) -> Path:
    """Unpack an unencrypted ``adb backup`` file (``.ab``) into ``out_dir``.

    Format: 4 text header lines (``ANDROID BACKUP``, version, compressed flag,
    encryption ``none``) followed by a (zlib-compressed) tar stream.
    """
    raw = Path(ab_path).read_bytes()
    lines = raw.split(b"\n", 4)
    if lines[0] != b"ANDROID BACKUP":
        raise ValueError("not an adb backup file")
    if lines[3] != b"none":
        raise ValueError("encrypted adb backups are not supported; re-run adb backup without a password")
    payload = lines[4]
    if lines[2] == b"1":
        payload = zlib.decompress(payload)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    with tarfile.open(fileobj=io.BytesIO(payload)) as tar:
        members = [m for m in tar.getmembers() if "consumerphysics" in m.name and m.name.endswith(".xml")]
        tar.extractall(out_dir, members=members)
    return out_dir


# --------------------------------------------------------------------------
# Blob format
# --------------------------------------------------------------------------

def decode_blob(b64: str) -> dict:
    """Base64 -> ``{"checksum": u32 LE, "data": body}`` (FirmwareUpgradeModel)."""
    raw = base64.b64decode("".join(b64.split()) + "=" * (-len("".join(b64.split())) % 4))
    if len(raw) < 4:
        raise ValueError("blob shorter than its 4-byte checksum prefix")
    return {"checksum": struct.unpack("<I", raw[:4])[0], "data": raw[4:], "raw": raw}


def save_blobs(found: dict, out_dir) -> list[Path]:
    """Write ``<name>.bin`` (body) + ``<name>.json`` (checksum, source, size)."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for name, rec in found.items():
        b = decode_blob(rec["b64"] if isinstance(rec, dict) else rec)
        (out_dir / f"{name}.bin").write_bytes(b["data"])
        meta = {"name": name, "file_id": FIRMWARE_FILES[name], "checksum": b["checksum"],
                "size": len(b["data"]), "source": rec.get("source") if isinstance(rec, dict) else None}
        (out_dir / f"{name}.json").write_text(json.dumps(meta, indent=1))
        written.append(out_dir / f"{name}.bin")
    return written


def load_blob_dir(directory) -> dict:
    """Load ``<name>.bin`` (+ optional ``.json``) files; also accepts ``<id>.bin``."""
    out = {}
    for p in sorted(Path(directory).glob("*.bin")):
        stem = p.stem
        name = stem if stem in ENUM_NAMES else next((n for n, i in FIRMWARE_FILES.items() if str(i) == stem), None)
        if name is None:
            continue
        meta = {}
        mp = p.with_suffix(".json")
        if mp.exists():
            meta = json.loads(mp.read_text())
        out[name] = {"data": p.read_bytes(), "checksum": meta.get("checksum"), "path": str(p)}
    return out


def match_checksums(blobs: dict, device_headers: dict) -> dict:
    """Compare blob checksum prefixes with ``READ_FILE_HEADER`` word 3 per file id.

    ``device_headers`` maps file id (int or str) -> checksum.  Returns
    ``{name: (blob_checksum, device_checksum, match_bool)}``.
    """
    res = {}
    for name, rec in blobs.items():
        fid = FIRMWARE_FILES[name]
        dev = device_headers.get(fid, device_headers.get(str(fid)))
        res[name] = (rec.get("checksum"), dev, rec.get("checksum") is not None and rec.get("checksum") == dev)
    return res


# --------------------------------------------------------------------------
# Triage
# --------------------------------------------------------------------------

def entropy(data: bytes) -> float:
    if not data:
        return 0.0
    n = len(data)
    return -sum(c / n * math.log2(c / n) for c in Counter(data).values())


def entropy_profile(data: bytes, window: int = 1024) -> list[float]:
    return [round(entropy(data[i : i + window]), 3) for i in range(0, len(data), window)]


def strings(data: bytes, min_len: int = 6, limit: int = 60) -> list[str]:
    found = re.findall(rb"[\x20-\x7e]{%d,}" % min_len, data)
    return [s.decode("ascii") for s in found[:limit]]



# Blackfin (BF51x/52x) boot-stream block header: 4 x u32 LE.
#   block_code: bits 31..24 = 0xAD signature; 23..16 = header XOR checksum;
#               15..0 = flags.  target_address, byte_count, argument follow.
_FLAGS = {0x8000: "FINAL", 0x4000: "FIRST", 0x2000: "INDIRECT", 0x1000: "IGNORE",
          0x0800: "INIT", 0x0400: "CALLBACK", 0x0200: "QUICKBOOT", 0x0100: "FILL",
          0x0020: "AUX", 0x0010: "SAVE"}


def parse_ldr(data: bytes, max_blocks: int = 8192) -> dict:
    """Parse a Blackfin LDR boot stream; return blocks and a validity verdict.

    A plaintext ``dsp_op`` is an LDR image: a chain of block headers whose code
    high byte is 0xAD, each followed by ``byte_count`` payload bytes (except
    FILL blocks).  If the stream parses cleanly to a FINAL block, it is not
    encrypted and can be disassembled.
    """
    blocks, off, n = [], 0, 0
    valid = False
    while off + 16 <= len(data) and n < max_blocks:
        code, addr, count, arg = struct.unpack_from("<IIII", data, off)
        sig = (code >> 24) & 0xFF
        flags = code & 0xFFFF
        if sig != 0xAD:
            break
        names = [nm for bit, nm in _FLAGS.items() if flags & bit]
        blocks.append({"offset": off, "address": addr, "count": count, "flags": names, "arg": arg})
        off += 16
        if not (flags & 0x0100):  # FILL blocks carry no payload
            off += count
        n += 1
        if flags & 0x8000:  # FINAL
            valid = True
            break
    return {"valid_ldr": valid, "n_blocks": len(blocks), "blocks": blocks[:64], "consumed": off}


def triage_blob(name: str, data: bytes) -> dict:
    """Summarise one blob: size, entropy, LDR structure, strings, verdict."""
    prof = entropy_profile(data)
    ent = round(entropy(data), 3)
    ldr = parse_ldr(data)
    strs = strings(data)
    # High entropy may be encryption, a signed container, compression or an
    # unknown packing. It cannot establish Lockbox usage by itself.
    if ldr["valid_ldr"] or (prof and min(prof) < 4.0):
        verdict = "plaintext (analysable)"
    elif ent > 7.5:
        verdict = "high-entropy opaque (encryption/compression/packing unresolved)"
    else:
        verdict = "unclear"
    return {"name": name, "size": len(data), "entropy": ent,
            "entropy_min_1k": min(prof) if prof else None,
            "entropy_max_1k": max(prof) if prof else None,
            "valid_ldr": ldr["valid_ldr"], "ldr_blocks": ldr["n_blocks"],
            "n_strings": len(strs), "sample_strings": strs[:10], "verdict": verdict}


def triage(blobs: dict) -> dict:
    """Triage every loaded blob (``{name: {"data": ...}}``)."""
    return {name: triage_blob(name, rec["data"]) for name, rec in blobs.items()}
