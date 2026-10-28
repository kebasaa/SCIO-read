"""Contributor bundles: scans from someone else's SCiO that can still be decoded.

The server decodes a scan only together with the device's own ``device_id``,
its ``i2s_tag_config`` and a white reference taken on the same unit. Bare blobs
from a home-grown capture script carry none of that, and it cannot be recovered
afterwards. A bundle is the fix: one command on the contributor's side, one on
ours::

    python -m scio contribute --name "closed cap" --count 5   # contributor
    python -m scio import scio_contrib_<device_id>_<stamp>.zip # owner

:func:`capture_bundle` reads the identity and firmware file headers, takes a white
reference first (the bundle starts with none), captures the scans with
:func:`session.capture` and zips them with a ``manifest.json``. No network and no
account are needed, and no location is recorded.

:func:`import_bundle` checks the hashes and that every record and white belong to
the device in the manifest, then *copies* them into ``01_rawdata/`` (append-only;
records already present are skipped). ``session.process_pending`` replays them.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import zipfile
from datetime import datetime
from pathlib import Path, PurePosixPath

from . import __version__, session, store
from .paths import portable_path

SCHEMA = "scio-contrib/1"
MANIFEST = "manifest.json"
SCANS_SUB = "scans"
WHITE_SUB = "white"


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _jsonable(value):
    """File headers come back keyed by int and may hold bytes; make them JSON-safe."""
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if isinstance(value, (bytes, bytearray)):
        return value.hex()
    return value


def _firmware_files(dev) -> dict:
    """File list + headers (read-only). Recorded, never required."""
    out = {}
    for key, reader in (("file_list", "read_file_list"), ("file_headers", "read_all_file_headers")):
        fn = getattr(dev, reader, None)
        if fn is None:
            continue
        try:
            out[key] = _jsonable(fn())
        except Exception as exc:     # a missing header must not cost the contributor the scans
            out[key] = {"error": f"{type(exc).__name__}: {exc}"}
    return out


def capture_bundle(dev, name: str, count: int = 1, out_dir=".", *, comment: str = "",
                   on_calibration_needed=None, before_scan=None) -> Path:
    """Capture *count* scans of one target into ``scio_contrib_<device_id>_<stamp>.zip``.

    *on_calibration_needed* is called with the calibration report before the white
    reference (put the cover on; return falsy to abort). *before_scan* is called
    with the 1-based scan number before each scan (place the target; return
    ``False`` to stop early). Returns the zip path; the unzipped folder is kept
    beside it.
    """
    if count < 1:
        raise ValueError("count must be at least 1")
    info = dev.read_device_info()
    missing = [k for k in ("device_id", "i2s_tag_config") if not info.get(k)]
    if missing:
        raise RuntimeError(f"device did not report {', '.join(missing)}; reconnect and retry. "
                           "Scans without it cannot be decoded.")
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    folder = Path(out_dir) / f"scio_contrib_{info['device_id']}_{stamp}"
    scans_dir, white_dir = folder / SCANS_SUB, folder / WHITE_SUB
    folder.mkdir(parents=True, exist_ok=False)
    firmware = _firmware_files(dev)

    written = []
    for i in range(1, count + 1):
        if before_scan is not None and before_scan(i) is False:
            break
        written.append(session.capture(
            dev, name, comment=comment, out_dir=scans_dir, wr_dir=white_dir,
            thresholds=dict(session.THRESHOLDS_FALLBACK, source="contributor bundle"),
            on_calibration_needed=on_calibration_needed, geolocate=False))
    if not written:
        raise RuntimeError("no scan was captured")

    def _entries(paths, sub):
        return [{"file": f"{sub}/{p.name}", "sha256": _sha256(p.read_bytes())} for p in paths]

    now = datetime.now().astimezone()
    manifest = {
        "schema": SCHEMA,
        "created_at": now.isoformat(timespec="seconds"),
        "utc_offset": now.strftime("%z"),
        "tool": {"package": "scio", "version": __version__},
        "device": info,
        "firmware_files": firmware,
        "target": {"name": name, "comment": comment, "count": len(written)},
        "white_references": _entries(sorted(white_dir.glob("*.json")), WHITE_SUB),
        "scans": _entries(written, SCANS_SUB),
        "location": "not recorded",
    }
    (folder / MANIFEST).write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    return Path(shutil.make_archive(str(folder), "zip", root_dir=folder))


# ----------------------------------------------------------------------- import
def _member(zf: zipfile.ZipFile, name: str, sub: str) -> bytes:
    """Read one manifest-listed member; refuse anything outside ``<sub>/<file>.json``."""
    p = PurePosixPath(name)
    if len(p.parts) != 2 or p.parts[0] != sub or p.suffix != ".json":
        raise ValueError(f"unexpected bundle member {name!r}")
    return zf.read(name)


def read_bundle(zip_path) -> dict:
    """Validate a bundle and return ``{manifest, whites:[(name, dict)], scans:[(name, dict)]}``."""
    with zipfile.ZipFile(zip_path) as zf:
        manifest = json.loads(zf.read(MANIFEST))
        if manifest.get("schema") != SCHEMA:
            raise ValueError(f"not a {SCHEMA} bundle")
        device = manifest.get("device") or {}
        dev_id = device.get("device_id")
        if not dev_id or not device.get("i2s_tag_config"):
            raise ValueError("bundle manifest has no device_id / i2s_tag_config")
        loaded = {}
        for key, sub in (("white_references", WHITE_SUB), ("scans", SCANS_SUB)):
            items = []
            for entry in manifest.get(key) or []:
                data = _member(zf, entry["file"], sub)
                if _sha256(data) != entry["sha256"]:
                    raise ValueError(f"hash mismatch for {entry['file']}")
                items.append((PurePosixPath(entry["file"]).name, json.loads(data)))
            loaded[key] = items
    if not loaded["white_references"]:
        raise ValueError("bundle has no white reference")
    if not loaded["scans"]:
        raise ValueError("bundle has no scans")
    for fname, wr in loaded["white_references"]:
        if (wr.get("device") or {}).get("device_id") != dev_id:
            raise ValueError(f"white {fname} is from another device")
    for fname, rec in loaded["scans"]:
        if rec.get("schema") != session.SCHEMA:
            raise ValueError(f"{fname} is not a {session.SCHEMA} record")
        rdev = rec.get("device") or {}
        if rdev.get("device_id") != dev_id or not rdev.get("i2s_tag_config"):
            raise ValueError(f"{fname} is from another device or has no i2s_tag_config")
        if not (rec.get("white_reference") or {}).get("blobs"):
            raise ValueError(f"{fname} has no white reference")
    return {"manifest": manifest, "whites": loaded["white_references"], "scans": loaded["scans"]}


def import_bundle(zip_path, scans_dir=session.SCANS_DIR, wr_dir=store.WR_DIR) -> dict:
    """Copy a validated bundle into the raw-data tree. Append-only and idempotent."""
    bundle = read_bundle(zip_path)
    zip_name = Path(zip_path).name
    scans_dir, wr_dir = Path(scans_dir), Path(wr_dir)
    wr_dir.mkdir(parents=True, exist_ok=True)

    known_wr = {}
    for p in wr_dir.glob("*.json"):
        try:
            known_wr[json.loads(p.read_text(encoding="utf-8")).get("wr_id")] = p
        except (OSError, ValueError):
            continue
    white_paths, whites_new = {}, []
    for fname, wr in bundle["whites"]:
        path = known_wr.get(wr.get("wr_id")) if wr.get("wr_id") else None
        if path is None:
            path = wr_dir / fname
            n = 2
            while path.exists():            # never overwrite an existing calibration
                path = wr_dir / f"{Path(fname).stem}_{n}.json"
                n += 1
            path.write_text(json.dumps(wr, indent=1), encoding="utf-8")
            whites_new.append(portable_path(path))
        white_paths[fname] = portable_path(path)

    known_uids = set()
    for p in scans_dir.glob("*.json") if scans_dir.is_dir() else []:
        try:
            known_uids.add(json.loads(p.read_text(encoding="utf-8")).get("scan_uid"))
        except (OSError, ValueError):
            continue
    imported, skipped = [], []
    for fname, rec in bundle["scans"]:
        if rec.get("scan_uid") in known_uids:
            skipped.append(fname)
            continue
        wr = rec["white_reference"]
        src_name = PurePosixPath(str(wr.get("source") or "")).name
        wr["source"] = white_paths.get(src_name, wr.get("source"))
        prov = rec.get("provenance") or {}
        rec["provenance"] = {**prov, "source": f"contributor bundle {zip_name}",
                             "contributor_source": prov.get("source"), "bundle_file": fname}
        imported.append(portable_path(session.write_record(rec, out_dir=scans_dir)))
    return {"device_id": bundle["manifest"]["device"]["device_id"],
            "firmware_version": bundle["manifest"]["device"].get("firmware_version"),
            "imported": imported, "skipped": skipped, "white_references": whites_new}
