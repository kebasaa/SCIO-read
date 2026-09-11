"""The scan workflow: capture, convert, process.

Capture and processing are deliberately **decoupled**. A scan is captured into a
self-contained record under ``01_rawdata/scans/`` with no network involved; the
Consumer Physics server turns it into a spectrum later - minutes or years later,
in a different place, from a different machine::

    rec = session.capture(dev, name="bark", comment="north-facing trunk")
    ...
    session.process_pending()          # when there is a network and an account

That matters because the vendor server is the only known way to get a spectrum
out of a SCiO blob, and it may disappear. A ``scio-scan/2`` record therefore
carries *everything the server asks for* - both blob encodings, the paired white
reference, the device id and i2s tag, both timestamps, the temperatures and the
calibration state - so a record is replayable on its own.

Records are additive. Nothing under ``01_rawdata/`` is ever modified or deleted:
:func:`convert_legacy` and :func:`extract_logs` *copy* older captures into the
canonical format and record where each came from in ``provenance``.
"""

from __future__ import annotations

import glob
import json
import re
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import cloud, logscan, store
from .paths import portable_path
from .store import (
    PROCESSED_DIR,
    SCAN_KEYS,
    SCANS_DIR,
    WHITE_KEYS,
    blob_bytes,
    blob_entry,
    now_iso,
)

SCHEMA = "scio-scan/2"
PROCESSED_SCHEMA = "scio-spectrum/1"

#: Used when the server has never been asked and no cache exists. The live values
#: for this device are ~1e9 minutes / 1e9 scans / 10000 degC, i.e. every rule off:
#: a white reference is needed only when none exists at all.
THRESHOLDS_FALLBACK = {"time_ms": 0, "scans": 0, "temperature": 0.0, "source": "fallback"}

_SLUG_RE = re.compile(r"[^A-Za-z0-9]+")


# --------------------------------------------------------------------- helpers
def _slug(text: str, limit: int = 40) -> str:
    return _SLUG_RE.sub("_", str(text or "scan")).strip("_")[:limit].lower() or "scan"


def annotate(name: str, scan_id: str | None = None, comment: str = "") -> dict:
    """The three user-supplied fields every canonical record must carry.

    ``scan_id`` is generated when omitted, but ``name`` is required: a record
    nobody can identify a year from now is the failure mode this guards against.
    """
    if not str(name).strip():
        raise ValueError("every scan needs a name - it is how you will find it later")
    return {
        "name": str(name).strip(),
        "scan_id": str(scan_id).strip() if str(scan_id or "").strip() else uuid.uuid4().hex[:12],
        "comment": str(comment or ""),
    }


def _white_section(white: dict | None, source: str | None = None) -> dict | None:
    """Normalize a white reference (``store.load_scan`` shape) into the record."""
    if white is None:
        return None
    meta = white.get("meta", {})
    return {
        "wr_id": meta.get("wr_id"),
        "sampled_white_at": meta.get("sampled_white_at"),
        "source": source or white.get("path"),
        "temperature_before": meta.get("temperature_before"),
        "temperature_after": meta.get("temperature_after"),
        "wr_temperature_app": store._wr_temperature(meta),
        "scans_since_calibration": meta.get("scans_since_calibration"),
        "validated": meta.get("validated"),
        "blobs": {k: blob_entry(v) for k, v in white["blobs"].items() if k in WHITE_KEYS},
    }


def build_record(annotation: dict, device: dict, blobs: dict, white: dict | None, *,
                 sampled_at: str | None = None, temperature: dict | None = None,
                 status_word: int | None = None, calibration: dict | None = None,
                 transport: str = "usb", provenance: dict | None = None,
                 spectrum: dict | None = None, extra: dict | None = None) -> dict:
    """Assemble a ``scio-scan/2`` record. Pure - does not touch the filesystem."""
    rec = {
        "schema": SCHEMA,
        "scan_uid": uuid.uuid4().hex,
        "annotation": annotation,
        "sampled_at": sampled_at or now_iso(),
        "created_at": now_iso(),
        "transport": transport,
        "device": device,
        "temperature": temperature or {},
        "status_word": status_word,
        "raw": {k: blob_entry(v) for k, v in blobs.items() if k in SCAN_KEYS},
        "white_reference": white,
        "calibration": calibration or {},
        "provenance": provenance or {},
        "reference_spectrum": spectrum,
        "unused_but_recorded": {
            "note": "Kept deliberately though unused by the current pipeline; "
                    "it costs nothing and may matter to a later decoding attempt.",
            "threshold_logic_status": (
                "The time/scans/temperature calibration rules come from the device-era "
                "app. Newer builds (consumer 1.3.8.554, Lab 1.3.12.144) abandoned them "
                "and use only NEVER/NO_NEED."),
        },
    }
    if extra:
        rec["unused_but_recorded"].update(extra)
    return rec


def record_filename(rec: dict) -> str:
    stamp = str(rec.get("sampled_at") or "")[:19].replace("-", "").replace(":", "").replace("T", "_")
    stamp = _SLUG_RE.sub("", stamp)[:15] or datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"{stamp}_{_slug(rec['annotation']['name'])}_{rec['annotation']['scan_id']}.json"


def write_record(rec: dict, out_dir=SCANS_DIR) -> Path:
    """Write a canonical record; never overwrites (``_2``, ``_3``, ... on collision)."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / record_filename(rec)
    n = 2
    while path.exists():
        path = out_dir / f"{path.stem}_{n}.json" if n == 2 else out_dir / f"{path.stem.rsplit('_', 1)[0]}_{n}.json"
        n += 1
    path.write_text(json.dumps(rec, indent=1), encoding="utf-8")
    return path


def load_record(path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def record_blobs(rec: dict) -> tuple[dict, dict]:
    """``(scan_blobs, white_blobs)`` as bytes, ready for :func:`cloud.build_scan_payload`."""
    scan = {k: blob_bytes(v) for k, v in rec.get("raw", {}).items()}
    wr = rec.get("white_reference") or {}
    white = {k: blob_bytes(v) for k, v in (wr.get("blobs") or {}).items()}
    return scan, white


def to_payload(rec: dict) -> dict:
    """Build the spectro-scan request body for a canonical record."""
    scan_b, white_b = record_blobs(rec)
    missing = [k for k in ("sample", "sample_dark") if k not in scan_b]
    missing += [k for k in ("sample_white", "sample_white_dark") if k not in white_b]
    if missing:
        raise ValueError(f"record is not processable, missing blobs: {missing}")
    dev = rec.get("device", {})
    i2s = dev.get("i2s_tag_config")
    if not i2s:
        raise ValueError("record has no i2s_tag_config; the server rejects an empty tag")
    return cloud.build_scan_payload(
        {"blobs": scan_b, "meta": {"sampled_at": rec.get("sampled_at")}},
        {"blobs": white_b,
         "meta": {"sampled_white_at": (rec["white_reference"] or {}).get("sampled_white_at")}},
        dev.get("device_id"), i2s,
    )


# --------------------------------------------------------------------- capture
def resolve_thresholds(device_id: str, token: str | None = None) -> dict:
    """Server thresholds if a token is given, else the cache, else the fallback."""
    if token:
        try:
            th = cloud.fetch_calibration_thresholds(token, device_id)
            store.cache_thresholds(device_id, th)
            return th
        except cloud.CloudError:
            pass
    return store.load_cached_thresholds(device_id) or dict(THRESHOLDS_FALLBACK)


def capture(dev, name: str, scan_id: str | None = None, comment: str = "", *,
            token: str | None = None, force_calibrate: bool = False,
            thresholds: dict | None = None, out_dir=SCANS_DIR, wr_dir=None,
            on_calibration_needed=None) -> Path:
    """Capture one scan from a live device into a canonical record. **No network.**

    *dev* is an open :class:`scio.usb.ScioUSB`. The white reference is reused from
    disk unless one is missing, stale by the thresholds in force, or
    *force_calibrate* is set; in that case *on_calibration_needed* is called with
    the calibration report so the caller can prompt for the cover to be put on
    (it must return truthy to proceed, and returning ``False`` aborts).

    ``token`` is optional and used only to refresh the calibration thresholds -
    the capture itself never needs it.
    """
    wr_dir = Path(wr_dir) if wr_dir is not None else store.WR_DIR
    info = dev.read_device_info()
    device_id = info.get("device_id")
    fw = info.get("firmware_version", 0)
    thresholds = thresholds or resolve_thresholds(device_id, token)

    cal = store.load_latest_calibration(device_id, wr_dir) if device_id else None
    t_before = dev.read_temperature()
    report = store.calibration_report(cal, t_before.get("cmos_t_app"), thresholds)
    need_wr = force_calibrate or report["status"] != "NO_NEED"

    if need_wr:
        if on_calibration_needed is not None and not on_calibration_needed(report):
            raise RuntimeError(f"white reference required ({report['status']}) but not taken")
        wr_before = dev.read_temperature()
        wr_blobs = dev.white_reference(fw)
        wr_after = dev.read_temperature()
        wr_path = store.save_calibration(wr_blobs, info, wr_before, wr_after,
                                         out_dir=wr_dir, thresholds=thresholds)
        cal = store.load_scan(wr_path)
        report = store.calibration_report(cal, t_before.get("cmos_t_app"), thresholds)
        report["captured_now"] = True
        t_before = dev.read_temperature()
    if cal is None:
        raise RuntimeError("no white reference available; a scan cannot be processed without one")

    scan = dev.sample_spectrum(fw)
    t_after = dev.read_temperature()
    if device_id:
        store.bump_scans_since_calibration(device_id, wr_dir)

    rec = build_record(
        annotate(name, scan_id, comment), info, scan["blobs"],
        _white_section(cal, portable_path(store.latest_calibration_path(device_id, wr_dir))),
        temperature={"scan_before": t_before, "scan_after": t_after},
        status_word=scan.get("status_word"),
        calibration={"status_at_scan": report["status"], "thresholds": thresholds,
                     "thresholds_source": thresholds.get("source", "unknown"),
                     "report": report},
        transport="usb",
        provenance={"source": "live capture", "n_responses": scan.get("n_responses"),
                    "notes": []},
    )
    return write_record(rec, out_dir)


# ------------------------------------------------------------------ conversion
def _naive_to_iso(text: str, offset_hours: int = 2) -> str:
    """``2023-03-30 08:26:26`` -> ISO with an offset (the captures are CEST)."""
    try:
        dt = datetime.strptime(str(text).strip(), "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return str(text)
    return dt.replace(tzinfo=timezone(timedelta(hours=offset_hours))).isoformat(timespec="milliseconds")


def _fixture_record(path: Path, white_hint: dict | None) -> dict | None:
    """A ``log_extracted`` fixture: already complete (all six blobs + spectrum)."""
    d = json.loads(path.read_text(encoding="utf-8"))
    b64 = d.get("b64_data", {})
    fx = store.load_fixture(path)
    scan_b = {k: v for k, v in fx["blobs"].items() if k in SCAN_KEYS}
    white_b = {k: v for k, v in fx["blobs"].items() if k in WHITE_KEYS}
    if "sample" not in scan_b or "sample_white" not in white_b:
        return None
    device = {"device_id": (b64.get("device_id") or "").upper() or None,
              "i2s_tag_config": b64.get("i2s_tag_config"),
              "device_info_raw": d.get("device", {})}
    spec = fx["spectrum"]
    return build_record(
        annotate(path.parent.name, path.stem[-6:], f"Recovered from a 2020/2021 app log ({path.parent.name})."),
        device, scan_b,
        {"wr_id": None, "sampled_white_at": b64.get("sampled_white_at"),
         "source": portable_path(path), "temperature_before": None, "temperature_after": None,
         "wr_temperature_app": None, "scans_since_calibration": None, "validated": None,
         "blobs": {k: blob_entry(v) for k, v in white_b.items()}},
        sampled_at=b64.get("sampled_at"),
        temperature={"scan_before": d.get("temperature"), "scan_after": None},
        transport="ble",
        calibration={"status_at_scan": "NO_NEED", "thresholds": None,
                     "thresholds_source": "not recorded (app-era capture)", "report": None},
        provenance={"source": "log_extracted fixture", "converted_from": portable_path(path),
                    "notes": ["White reference is the one the app itself paired with this scan.",
                              "mobile_mac_address is not carried over; canonical records use the "
                              "synthetic 02:00:00:00:00:00 that build_scan_payload sends."]},
        spectrum={"source": "Consumer Physics server, at capture time",
                  "reflectance": spec} if spec else None,
    )


def _legacy_2023_record(path: Path, white: dict, white_src: str) -> dict | None:
    """2023 ``scan_*.json``: URL-safe base64, naive timestamp, no device_id, no WR."""
    d = json.loads(path.read_text(encoding="utf-8"))
    raw = d.get("raw_data", {})
    blobs = {k: bytes.fromhex(raw[k]) for k in SCAN_KEYS if isinstance(raw.get(k), str)}
    if "sample" not in blobs:
        return None
    devsrc = d.get("device", {})
    aptina = str(devsrc.get("aptinaId") or "")
    device = {"device_id": aptina[-16:].upper() or None,
              "i2s_tag_config": devsrc.get("i2s_tag_config"),
              "firmware_version": devsrc.get("firmwareVersion"),
              "dsp_id": devsrc.get("deviceDspId"), "ble_id": devsrc.get("deviceBleId"),
              "device_name": devsrc.get("device_name"), "device_info_raw": devsrc}
    t = d.get("temperature", {})
    sampled_at = _naive_to_iso(t.get("sampled_at") or raw.get("sampled_at"))
    return build_record(
        annotate(_slug(path.stem.replace("scan_", "")), path.stem[-8:],
                 "2023 USB capture; no white reference was taken at the time."),
        device, blobs, _white_section(white, white_src),
        sampled_at=sampled_at,
        temperature={"scan_before": {"cmos_t": t.get("t_cmos_before"), "chip_t": t.get("t_chip_before"),
                                     "obj_t": t.get("t_obj_before")},
                     "scan_after": {"cmos_t": t.get("t_cmos_after"), "chip_t": t.get("t_chip_after"),
                                    "obj_t": t.get("t_obj_after")}},
        calibration={"status_at_scan": "NEVER", "thresholds": None,
                     "thresholds_source": "not recorded (2023 capture)", "report": None},
        provenance={"source": "01_rawdata/scan_json (2023 series)",
                    "converted_from": portable_path(path),
                    "notes": [
                        "PHYSICALLY INVALID REFLECTANCE: no white reference exists for 2023, so "
                        f"this record borrows the {white_src} white reference taken years later. "
                        "The server will return a spectrum, but it is not a calibrated measurement.",
                        "device_id derived from device.aptinaId (last 16 hex, uppercased); "
                        "lowercase is rejected by the API with HTTP 404.",
                        "Blobs re-encoded from the authoritative hex: the original file stored "
                        "URL-safe unpadded base64, which the server does not accept.",
                        "sampled_at was naive local time; +02:00 (CEST) assumed."]},
    )


def _scan1_record(path: Path, white: dict | None, white_src: str | None,
                  i2s_fallback: str | None) -> dict | None:
    """2026 ``scio-scan/1``: three blobs, needs the WR attached (and sometimes an i2s tag)."""
    d = json.loads(path.read_text(encoding="utf-8"))
    blobs = {k: bytes.fromhex(v) for k, v in d.get("raw_hex", {}).items() if k in SCAN_KEYS}
    if "sample" not in blobs:
        return None
    device = dict(d.get("device", {}))
    notes = []
    if not device.get("i2s_tag_config") and i2s_fallback:
        device["i2s_tag_config"] = i2s_fallback
        notes.append("i2s_tag_config was empty in the original file (the BLE-ID read failed at "
                     f"capture time); filled in from the same device's white reference: "
                     f"{i2s_fallback}. Without it the server rejects the scan.")
    temp = d.get("temperature", {})
    if "before" in temp or "after" in temp:
        temperature = {"scan_before": temp.get("before"), "scan_after": temp.get("after")}
    else:
        temperature = {"scan_before": temp or None, "scan_after": None}
        notes.append("Only a single temperature reading was stored, not before/after.")
    label = d.get("target_label") or path.stem.replace("scan_", "")
    comment = d.get("operator_notes") or ""
    extra = {k: d[k] for k in ("target_label", "replicate_index", "capture_event") if k in d}
    return build_record(
        annotate(_slug(label), path.stem[-10:], comment),
        device, blobs, _white_section(white, white_src),
        sampled_at=d.get("sampled_at"),
        temperature=temperature, status_word=d.get("status_word"),
        calibration={"status_at_scan": None, "thresholds": None,
                     "thresholds_source": "not recorded at capture time", "report": None},
        provenance={"source": "01_rawdata/scan_json (scio-scan/1)",
                    "converted_from": portable_path(path), "notes": notes},
        extra=extra or None,
    )


def convert_legacy(scan_dir=store.SCAN_DIR, out_dir=SCANS_DIR, fixture_dir=store.FIXTURE_DIR,
                   device_id: str = "8032AB45611198F1") -> list[Path]:
    """Copy every convertible legacy capture into ``01_rawdata/scans/``.

    Reads only; the originals stay exactly where and as they are. Returns the
    paths written (already-converted scans are skipped, so this is idempotent).
    """
    out_dir = Path(out_dir)
    done = _converted_sources(out_dir)
    wr_path = store.latest_calibration_path(device_id)
    white = store.load_scan(wr_path) if wr_path else None
    white_src = portable_path(wr_path) if wr_path else None
    i2s_fallback = (white or {}).get("device", {}).get("i2s_tag_config")

    written = []
    for path in sorted(Path(fixture_dir).glob("*/*.json")):
        if portable_path(path) in done:
            continue
        rec = _fixture_record(path, white)
        if rec:
            written.append(write_record(rec, out_dir))

    for path in sorted(Path(scan_dir).glob("scan_*.json")):
        if portable_path(path) in done:
            continue
        d = json.loads(path.read_text(encoding="utf-8"))
        if d.get("schema") == "scio-scan/1":
            rec = _scan1_record(path, white, white_src, i2s_fallback)
        else:
            if white is None:
                continue
            rec = _legacy_2023_record(path, white, white_src)
        if rec:
            written.append(write_record(rec, out_dir))
    return written


def extract_logs(log_dir=store.LOG_DIR, out_dir=SCANS_DIR) -> list[Path]:
    """Convert scans still sitting inside the raw logcat dumps.

    ``archive/notebooks/02_extract_log_scan.ipynb`` only wrote out scans the server
    had answered, so scans with no reply in the log were never extracted. This
    takes all of them, and skips any whose sample blob already exists as a
    canonical record.
    """
    out_dir = Path(out_dir)
    seen = {rec["raw"]["sample"]["hex"] for rec in _iter_records(out_dir) if "sample" in rec.get("raw", {})}
    written = []
    for scan in logscan.parse_logs(log_dir):
        req = scan["request"]
        scan_b, white_b = logscan.blobs_from_request(req)
        if scan_b["sample"].hex() in seen:
            continue
        seen.add(scan_b["sample"].hex())
        source = Path(scan["log"]).stem.replace("log_", "")
        device = {**scan["device"],
                  "device_id": (req.get("device_id") or "").upper() or None,
                  "i2s_tag_config": req.get("i2s_tag_config")}
        rec = build_record(
            annotate(_slug(source), f"log{scan['scan_index']:02d}",
                     f"Recovered from app log {Path(scan['log']).name}."),
            device, scan_b,
            {"wr_id": None, "sampled_white_at": req.get("sampled_white_at"),
             "source": scan["log"], "temperature_before": None, "temperature_after": None,
             "wr_temperature_app": None, "scans_since_calibration": None, "validated": None,
             "blobs": {k: blob_entry(v) for k, v in white_b.items()}},
            sampled_at=req.get("sampled_at"),
            temperature={"scan_before": scan.get("temperature"), "scan_after": None},
            transport="ble",
            calibration={"status_at_scan": "NO_NEED", "thresholds": None,
                         "thresholds_source": "not recorded (app-era capture)", "report": None},
            provenance={"source": "logcat dump", "converted_from": scan["log"],
                        "notes": ["White reference is the one the app itself paired with this scan.",
                                  "mobile_mac_address / mobile_GPS from the original request body "
                                  "are deliberately not carried over."]},
            spectrum={"source": "Consumer Physics server, at capture time",
                      "reflectance": scan["spectrum"]} if scan.get("spectrum") else None,
        )
        written.append(write_record(rec, out_dir))
    return written


def _iter_records(directory=SCANS_DIR):
    for p in sorted(Path(directory).glob("*.json")):
        try:
            yield json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue


def _converted_sources(directory=SCANS_DIR) -> set[str]:
    return {rec.get("provenance", {}).get("converted_from")
            for rec in _iter_records(directory)} - {None}


# ------------------------------------------------------------------ processing
def process(raw_path, token: str, out_dir=PROCESSED_DIR) -> Path:
    """Send one canonical record to the server and write the record + its spectrum.

    JSON only. The record carries the wavelength axis, the reflectance, the
    annotation and the whole originating scan, so a CSV alongside it would be a
    lossy second copy of the same numbers with a second format to keep in step.
    """
    rec = load_record(raw_path)
    payload = to_payload(rec)
    resp = cloud.analyze_scan(token, payload)
    wl, refl = cloud.spectrum_from_response(resp)

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out = {
        "schema": PROCESSED_SCHEMA,
        "processed_at": now_iso(),
        "source_record": portable_path(raw_path),
        "scan_uid": rec.get("scan_uid"),
        "annotation": rec.get("annotation"),
        "spectrum": {"wavelength_nm": wl, "reflectance": refl,
                     "n_points": len(refl),
                     "range_nm": [wl[0], wl[-1]] if wl else None},
        "server": {"endpoint": cloud.SPECTRO_URL,
                   "request_meta": {k: v for k, v in payload.items() if not k.startswith("sample")},
                   "response_meta": {k: v for k, v in resp.items() if k != "spectrum"}},
        "scan": rec,
    }
    path = Path(out_dir) / (Path(raw_path).stem + "_spectrum.json")
    path.write_text(json.dumps(out, indent=1), encoding="utf-8")
    return path


def pending(scans_dir=SCANS_DIR, processed_dir=PROCESSED_DIR) -> list[Path]:
    """Canonical records with no processed counterpart yet."""
    done = {p.stem[: -len("_spectrum")] for p in Path(processed_dir).glob("*_spectrum.json")}
    return [p for p in sorted(Path(scans_dir).glob("*.json")) if p.stem not in done]


def process_pending(token=None, limit: int | None = None, pause: float = 0.0,
                    scans_dir=SCANS_DIR, processed_dir=PROCESSED_DIR,
                    on_result=None) -> list[dict]:
    """Upload the backlog. This is the deferred half of the decoupled workflow.

    ``token`` may be a string or a callable; a callable is invoked per scan
    because access tokens are short-lived (``expires_in=14``). Failures are
    recorded and do not stop the run - one unusable record should not block the
    rest of a backlog.
    """
    from . import credentials
    if token is None:
        token = credentials.get_token
    todo = pending(scans_dir, processed_dir)
    if limit:
        todo = todo[:limit]
    results = []
    for i, path in enumerate(todo):
        tok = token() if callable(token) else token
        try:
            out = process(path, tok, processed_dir)
            row = {"scan": portable_path(path), "processed": portable_path(out), "error": None}
        except (cloud.CloudError, ValueError) as exc:
            row = {"scan": portable_path(path), "processed": None, "error": str(exc)}
        results.append(row)
        if on_result:
            on_result(row)
        if pause and i < len(todo) - 1:
            import time
            time.sleep(pause)
    return results


def summary(scans_dir=SCANS_DIR, processed_dir=PROCESSED_DIR) -> dict:
    """Counts for a quick 'what is in the store' view."""
    recs = list(_iter_records(scans_dir))
    return {
        "scans": len(recs),
        "with_white_reference": sum(1 for r in recs if r.get("white_reference")),
        "with_reference_spectrum": sum(1 for r in recs if r.get("reference_spectrum")),
        "processable": sum(1 for r in recs if _processable(r)),
        "processed": len(list(Path(processed_dir).glob("*_spectrum.json"))),
        "pending": len(pending(scans_dir, processed_dir)),
        "by_source": _count(r.get("provenance", {}).get("source", "unknown") for r in recs),
    }


def _processable(rec: dict) -> bool:
    try:
        to_payload(rec)
        return True
    except (ValueError, KeyError):
        return False


def _count(values) -> dict:
    out: dict[str, int] = {}
    for v in values:
        out[v] = out.get(v, 0) + 1
    return dict(sorted(out.items()))
