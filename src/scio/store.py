"""On-disk formats: base64 wrapping, fixtures, scan / white-reference files.

Base64: the app used Android ``Base64.DEFAULT`` (standard alphabet, ``=``
padding, a newline every 76 characters).  The old USB notebook used URL-safe
base64 instead; :func:`unwrap_b64` accepts both so legacy files still load.
"""

from __future__ import annotations

import base64
import json
import uuid
from datetime import datetime
from pathlib import Path

from .paths import REPOSITORY_ROOT, portable_path

SCAN_KEYS = ("sample", "sample_dark", "sample_gradient")
WHITE_KEYS = ("sample_white", "sample_white_dark", "sample_white_gradient")
DEFAULT_ROOT = REPOSITORY_ROOT
RAW_DIR = DEFAULT_ROOT / "01_rawdata"
FIXTURE_DIR = RAW_DIR / "log_extracted"
SCAN_DIR = RAW_DIR / "scan_json"
WR_DIR = RAW_DIR / "scan_json_calibration"
DEVICE_FILES_DIR = RAW_DIR / "device_files"
LOG_DIR = RAW_DIR / "log_files"
# Canonical, self-contained scan records (``scio-scan/2``); see scio.session.
SCANS_DIR = RAW_DIR / "scans"
PROCESSED_DIR = DEFAULT_ROOT / "02_processed_data"


def wrap_b64(data: bytes) -> str:
    """Standard base64 with a newline every 76 chars (Android Base64.DEFAULT)."""
    s = base64.b64encode(bytes(data)).decode("ascii")
    return "\n".join(s[i : i + 76] for i in range(0, len(s), 76)) + "\n"


def unwrap_b64(text: str) -> bytes:
    """Decode standard or URL-safe base64, ignoring whitespace and padding."""
    compact = "".join(str(text).split())
    compact += "=" * (-len(compact) % 4)
    return base64.urlsafe_b64decode(compact.replace("+", "-").replace("/", "_"))


def now_iso() -> str:
    """Local time with milliseconds and offset, e.g. 2021-10-20T10:58:58.729+03:00."""
    return datetime.now().astimezone().isoformat(timespec="milliseconds")


def load_fixture(path) -> dict:
    """Load a ``log_extracted`` fixture (raw bytes + server spectrum).

    Returns ``blobs`` (dict of bytes for the six blob keys present), ``spectrum``
    (list of 331 floats or None), ``device`` and ``meta`` (the original JSON).
    """
    d = json.loads(Path(path).read_text(encoding="utf-8"))
    blobs = {}
    b64 = d.get("b64_data", {})
    raw = d.get("raw_data", {})
    for k in SCAN_KEYS + WHITE_KEYS:
        if k in b64 and isinstance(b64[k], str):
            blobs[k] = unwrap_b64(b64[k])
        elif k in raw and isinstance(raw[k], str):
            blobs[k] = bytes.fromhex("".join(raw[k].split()))
    spec = d.get("spec_data")
    if isinstance(spec, str):
        spec = json.loads(spec)
    return {"path": portable_path(path), "blobs": blobs, "spectrum": spec, "device": d.get("device", {}), "meta": d}


def load_fixtures(directory=FIXTURE_DIR) -> list[dict]:
    return [load_fixture(p) for p in sorted(Path(directory).glob("*/*.json"))]


def load_scan(path) -> dict:
    """Load a scan file (legacy ``raw_data``/``b64_data`` or ``scio-scan/1``)."""
    d = json.loads(Path(path).read_text(encoding="utf-8"))
    blobs = {}
    if d.get("schema", "").startswith("scio-"):
        for k, v in d.get("raw_hex", {}).items():
            blobs[k] = bytes.fromhex(v)
    else:
        for k in SCAN_KEYS + WHITE_KEYS:
            if k in d.get("raw_data", {}):
                blobs[k] = bytes.fromhex(d["raw_data"][k])
            elif k in d.get("b64_data", {}):
                blobs[k] = unwrap_b64(d["b64_data"][k])
    return {"path": portable_path(path), "blobs": blobs, "device": d.get("device", {}), "meta": d}


def blob_entry(data: bytes) -> dict:
    """One blob as ``{size, hex, b64}`` - the canonical (``scio-scan/2``) shape.

    Both encodings are kept on purpose: ``hex`` is the authoritative bytes and
    ``b64`` is byte-for-byte what the server expects, so a record can be
    replayed years later without re-deriving the app's base64 conventions.
    """
    data = bytes(data)
    return {"size": len(data), "hex": data.hex(), "b64": wrap_b64(data)}


def blob_bytes(entry: dict | str) -> bytes:
    """Inverse of :func:`blob_entry`; accepts a bare hex/base64 string too."""
    if isinstance(entry, str):
        try:
            return bytes.fromhex("".join(entry.split()))
        except ValueError:
            return unwrap_b64(entry)
    if entry.get("hex"):
        return bytes.fromhex("".join(entry["hex"].split()))
    return unwrap_b64(entry["b64"])


def _blob_record(blobs: dict) -> dict:
    return {
        "raw_hex": {k: v.hex() for k, v in blobs.items()},
        "b64": {k: wrap_b64(v) for k, v in blobs.items()},
        "sizes": {k: len(v) for k, v in blobs.items()},
    }


def save_scan(blobs: dict, device: dict, temperatures: dict, status_word: int | None,
              calibration_file: str | None = None, out_dir=SCAN_DIR, stamp: str | None = None,
              extra_meta: dict | None = None) -> Path:
    """Write a ``scio-scan/1`` file with the three raw blobs and metadata."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = stamp or datetime.now().strftime("%Y%m%d_%H%M%S")
    rec = {
        "schema": "scio-scan/1",
        "device": device,
        "sampled_at": now_iso(),
        "temperature": temperatures,
        "status_word": status_word,
        "calibration_file": portable_path(calibration_file) if calibration_file else None,
        "transport": "usb",
        **_blob_record(blobs),
    }
    if extra_meta:
        protected = {"schema", "raw_hex", "b64", "sizes"}
        overlap = protected.intersection(extra_meta)
        if overlap:
            raise ValueError(f"extra_meta cannot replace protected fields: {sorted(overlap)}")
        rec.update(extra_meta)
    path = out_dir / f"scan_{stamp}.json"
    path.write_text(json.dumps(rec, indent=1), encoding="utf-8")
    return path


def save_calibration(blobs: dict, device: dict, temp_before: dict, temp_after: dict,
                     out_dir=WR_DIR, stamp: str | None = None,
                     thresholds: dict | None = None, validated: dict | None = None) -> Path:
    """Write a white-reference file as ``YYYYMMDD_HHMM_calibration.json``.

    Calibration history is never destroyed: the filename carries the timestamp,
    the same timestamp is stored inside, and a same-minute collision appends
    ``_2``, ``_3``, ... rather than overwriting. There is deliberately **no**
    ``*_latest.json`` copy - :func:`load_latest_calibration` computes the newest.

    ``blobs`` must use the keys sample_white / sample_white_dark / sample_white_gradient.
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = stamp or datetime.now().strftime("%Y%m%d_%H%M")
    fw = device.get("firmware_version") or 0

    def _avg(key):
        a, b = temp_before.get(key), temp_after.get(key)
        return (a + b) / 2.0 if a is not None and b is not None else a

    rec = {
        "schema": "scio-wr/2",
        "wr_id": uuid.uuid4().hex,
        "device": device,
        "sampled_white_at": now_iso(),
        "file_timestamp": stamp,
        "temperature_before": temp_before,
        "temperature_after": temp_after,
        # what isCalibrationNeeded actually compares: mean of the app-truncated Aptina values
        "wr_temperature_avg_app": _avg("cmos_t_app"),
        "wr_temperature_avg_float": _avg("cmos_t"),
        "scans_since_calibration": 0,
        "thresholds_in_force": thresholds,
        "validated": validated,
        "transport": "usb",
        "unused_but_recorded": {
            "note": "Kept deliberately though unused, may be useful later.",
            "ready_for_wr_supported": bool(fw >= 144),
            "ready_for_wr_cmds": {"READY_FOR_WR": "0x0E", "CLEAR_READY_FOR_WR": "0x11",
                                  "purpose": "LED/UX hint so the device button can trigger a WR"},
            "calibrate_status_values_never_returned": ["USER", "EXCEED_BEFORE_BATCH_SCAN_LIMIT"],
            "threshold_logic_status": ("Implemented per the device-era app; newer app builds "
                                        "(consumer 1.3.8.554, Lab 1.3.12.144) abandoned the "
                                        "time/scans/temperature rules and use only NEVER/NO_NEED."),
        },
        **_blob_record(blobs),
    }
    path = out_dir / f"{stamp}_calibration.json"
    n = 2
    while path.exists():                      # never overwrite an existing calibration
        path = out_dir / f"{stamp}_calibration_{n}.json"
        n += 1
    path.write_text(json.dumps(rec, indent=1), encoding="utf-8")
    return path


def list_calibrations(device_id: str | None = None, wr_dir=WR_DIR) -> list[Path]:
    """All calibration files (new ``*_calibration*.json`` and legacy ``wr_*.json``)."""
    wr_dir = Path(wr_dir)
    if not wr_dir.exists():
        return []
    paths = sorted(wr_dir.glob("*_calibration*.json")) + sorted(wr_dir.glob("wr_*.json"))
    out = []
    for p in paths:
        if p.name.endswith("_latest.json"):   # legacy duplicate; skip, the original is present
            continue
        if device_id is None:
            out.append(p)
            continue
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if (d.get("device") or {}).get("device_id") == device_id:
            out.append(p)
    return out


def latest_calibration_path(device_id: str, wr_dir=WR_DIR) -> Path | None:
    """Real filesystem path of the newest calibration for a device (or None)."""
    best, best_key = None, None
    for p in list_calibrations(device_id, wr_dir):
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        # Order by the true WR timestamp, tie-broken by the filename timestamp then
        # the name, so same-second saves still order deterministically.
        key = (d.get("sampled_white_at") or "", d.get("file_timestamp") or "", p.name)
        if best_key is None or key > best_key:
            best, best_key = p, key
    return best


def load_latest_calibration(device_id: str, wr_dir=WR_DIR) -> dict | None:
    """Newest calibration for a device, computed - nothing is ever overwritten."""
    p = latest_calibration_path(device_id, wr_dir)
    return load_scan(p) if p is not None else None


def bump_scans_since_calibration(device_id: str, wr_dir=WR_DIR) -> int | None:
    """Increment the scan counter on the newest calibration (client-side bookkeeping)."""
    p = latest_calibration_path(device_id, wr_dir)
    if p is None:
        return None
    d = json.loads(p.read_text(encoding="utf-8"))
    d["scans_since_calibration"] = int(d.get("scans_since_calibration", 0)) + 1
    p.write_text(json.dumps(d, indent=1), encoding="utf-8")
    return d["scans_since_calibration"]


THRESHOLD_CACHE = WR_DIR / "calibration_thresholds_cache.json"


def cache_thresholds(device_id: str, thresholds: dict, path=THRESHOLD_CACHE) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    all_ = {}
    if path.exists():
        try:
            all_ = json.loads(path.read_text(encoding="utf-8"))
        except ValueError:
            all_ = {}
    all_[device_id] = thresholds
    path.write_text(json.dumps(all_, indent=1), encoding="utf-8")
    return path


def load_cached_thresholds(device_id: str, path=THRESHOLD_CACHE) -> dict | None:
    path = Path(path)
    if not path.exists():
        return None
    try:
        entry = json.loads(path.read_text(encoding="utf-8")).get(device_id)
    except ValueError:
        return None
    if entry:
        entry = {**entry, "source": "cache"}
    return entry


def calibration_status(cal: dict | None, cmos_t_now: float | None, thresholds: dict) -> str:
    """Mirror ScioInternalDevice.isCalibrationNeeded.

    ``thresholds`` = {"time_ms", "scans", "temperature"}; a value <= 0 disables
    that check.  Returns NEVER / TIME_THRESHOLD / EXCEED_SCANS_LIMIT /
    TEMP_THRESHOLD / NO_NEED.
    """
    if cal is None:
        return "NEVER"
    meta = cal["meta"]
    t_ms = thresholds.get("time_ms", 0)
    if t_ms > 0:
        then = datetime.fromisoformat(meta["sampled_white_at"])
        age_ms = (datetime.now().astimezone() - then).total_seconds() * 1000
        if age_ms > t_ms:
            return "TIME_THRESHOLD"
    n = thresholds.get("scans", 0)
    if n > 0 and meta.get("scans_since_calibration", 0) >= n:
        return "EXCEED_SCANS_LIMIT"
    dt = thresholds.get("temperature", 0)
    if dt > 0 and cmos_t_now is not None:
        wr_t = _wr_temperature(meta)
        if wr_t is not None and abs(cmos_t_now - wr_t) > dt:
            return "TEMP_THRESHOLD"
    return "NO_NEED"


def _wr_temperature(meta: dict):
    """WR temperature the app compares: mean of the before/after app-truncated Aptina."""
    if meta.get("wr_temperature_avg_app") is not None:
        return meta["wr_temperature_avg_app"]
    tb_d, ta_d = meta.get("temperature_before") or {}, meta.get("temperature_after") or {}
    for key in ("cmos_t_app", "cmos_t"):     # prefer the app value, fall back for old files
        tb = tb_d.get(key)
        if tb is not None:
            return (tb + ta_d.get(key, tb)) / 2.0
    return None


def calibration_report(cal: dict | None, cmos_t_now: float | None, thresholds: dict) -> dict:
    """`calibration_status` plus the supporting numbers, for display and records."""
    status = calibration_status(cal, cmos_t_now, thresholds)
    rep = {"status": status, "thresholds": thresholds,
           "scan_temp_now_app": cmos_t_now, "wr_temperature": None,
           "wr_age_ms": None, "scans_since_calibration": None, "temp_delta": None}
    if cal is not None:
        meta = cal["meta"]
        rep["wr_id"] = meta.get("wr_id")
        rep["sampled_white_at"] = meta.get("sampled_white_at")
        rep["scans_since_calibration"] = meta.get("scans_since_calibration", 0)
        rep["wr_temperature"] = _wr_temperature(meta)
        try:
            then = datetime.fromisoformat(meta["sampled_white_at"])
            rep["wr_age_ms"] = int((datetime.now().astimezone() - then).total_seconds() * 1000)
        except (KeyError, ValueError):
            pass
        if rep["wr_temperature"] is not None and cmos_t_now is not None:
            rep["temp_delta"] = abs(cmos_t_now - rep["wr_temperature"])
    return rep


def save_device_files(records: dict, out_dir=DEVICE_FILES_DIR) -> Path:
    """Store device info + file list + file headers captured over USB."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"device_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    path.write_text(json.dumps(records, indent=1), encoding="utf-8")
    return path
