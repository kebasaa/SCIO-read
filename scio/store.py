"""On-disk formats: base64 wrapping, fixtures, scan / white-reference files.

Base64: the app used Android ``Base64.DEFAULT`` (standard alphabet, ``=``
padding, a newline every 76 characters).  The old USB notebook used URL-safe
base64 instead; :func:`unwrap_b64` accepts both so legacy files still load.
"""

from __future__ import annotations

import base64
import json
from datetime import datetime
from pathlib import Path

from .paths import portable_path

SCAN_KEYS = ("sample", "sample_dark", "sample_gradient")
WHITE_KEYS = ("sample_white", "sample_white_dark", "sample_white_gradient")
DEFAULT_ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = DEFAULT_ROOT / "01_rawdata"
FIXTURE_DIR = RAW_DIR / "log_extracted"
SCAN_DIR = RAW_DIR / "scan_json"
WR_DIR = RAW_DIR / "scan_json_calibration"
DEVICE_FILES_DIR = RAW_DIR / "device_files"


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
                     out_dir=WR_DIR, stamp: str | None = None) -> Path:
    """Write a ``scio-wr/1`` white-reference file and refresh ``*_latest.json``.

    ``blobs`` must use the keys sample_white / sample_white_dark / sample_white_gradient.
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = stamp or datetime.now().strftime("%Y%m%d_%H%M%S")
    dev_id = device.get("device_id", "unknown")
    rec = {
        "schema": "scio-wr/1",
        "device": device,
        "sampled_white_at": now_iso(),
        "temperature_before": temp_before,
        "temperature_after": temp_after,
        "scans_since_calibration": 0,
        "transport": "usb",
        **_blob_record(blobs),
    }
    path = out_dir / f"wr_{dev_id}_{stamp}.json"
    text = json.dumps(rec, indent=1)
    path.write_text(text, encoding="utf-8")
    (out_dir / f"wr_{dev_id}_latest.json").write_text(text, encoding="utf-8")
    return path


def load_latest_calibration(device_id: str, wr_dir=WR_DIR) -> dict | None:
    p = Path(wr_dir) / f"wr_{device_id}_latest.json"
    return load_scan(p) if p.exists() else None


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
        tb = meta["temperature_before"].get("cmos_t")
        ta = meta["temperature_after"].get("cmos_t", tb)
        if tb is not None and abs(cmos_t_now - (tb + ta) / 2) > dt:
            return "TEMP_THRESHOLD"
    return "NO_NEED"


def save_device_files(records: dict, out_dir=DEVICE_FILES_DIR) -> Path:
    """Store device info + file list + file headers captured over USB."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"device_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    path.write_text(json.dumps(records, indent=1), encoding="utf-8")
    return path
