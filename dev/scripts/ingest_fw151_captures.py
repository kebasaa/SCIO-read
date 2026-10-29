"""Ingest the fw-151 contributor captures (email/scio-fw151-captures-20261027/).

They arrived as bare blobs: 1 scan (split frames + the raw USB stream) and a 5-scan
multiscan, each dark/sample/gradient = 1800/1800/1416 B. No device_id, no white
reference. The server binds every blob to the request device_id, so nothing can be
decoded until the contributor supplies identity and calibration. Matching file
versions in an outside report do not establish this unit's identity or i2s tag.

  (default)            parse + validate, cross-check the split frames against _raw.bin,
                       write parsed.json. No server.
  --run [--live]       build scio-scan/2 records with --device-id/--i2s and a white
                       (--white <scio-wr/2 json>), replay
                       20 s apart and promote only HTTP 200 + 331 finite bands.

    python dev/scripts/ingest_fw151_captures.py --output dev/analysis_output/fw151_captures_20261028
    python dev/scripts/ingest_fw151_captures.py --output dev/analysis_output/<run> --run --live \\
        --device-id <ID> --i2s <verified tag> --white <their white json>
"""
import argparse
import json
import re
import struct
import time
from datetime import datetime
from pathlib import Path

import _bootstrap  # noqa: F401
import numpy as np
from scio import cloud, credentials, session, store
from scio.paths import portable_path
from scio_offline import research as r

CAPTURE_DIR = r.ROOT / "email" / "scio-fw151-captures-20261027"
EXPECT_SIZES = {"dark": 1800, "sample": 1800, "gradient": 1416}
ROLES = ("dark", "sample", "gradient")
ROLE_SCAN = {"dark": "sample_dark", "sample": "sample", "gradient": "sample_gradient"}
ROLE_WHITE = {"dark": "sample_white_dark", "sample": "sample_white", "gradient": "sample_white_gradient"}


def split_usb_stream(raw: bytes) -> list:
    """Frames of a ``ba <cmd> <len u16 LE> <payload>`` USB stream (no seq byte on replies)."""
    frames, i = [], 0
    while i < len(raw):
        if raw[i] != 0xBA or i + 4 > len(raw):
            raise ValueError(f"no frame marker at offset {i}")
        if raw[i + 1] != 0x02:
            raise ValueError(f"unexpected command at offset {i}")
        (n,) = struct.unpack_from("<H", raw, i + 2)
        if not n or i + 4 + n > len(raw):
            raise ValueError(f"empty or truncated payload at offset {i}")
        frames.append(raw[i + 4:i + 4 + n])
        i += 4 + n
    return frames


def _check(scan_id, frames):
    if set(frames) != set(ROLES):
        raise ValueError(f"{scan_id}: requires exactly dark/sample/gradient")
    for role in ROLES:
        if len(frames[role]) != EXPECT_SIZES[role]:
            raise ValueError(f"{scan_id} {role}: {len(frames[role])} B, expected {EXPECT_SIZES[role]}")


def parse_captures(cap_dir: Path = CAPTURE_DIR) -> dict:
    def metadata(path):
        meta = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(meta, dict) or not isinstance(meta.get("time"), str):
            raise ValueError(f"{path.name}: missing capture time")
        datetime.fromisoformat(meta["time"])
        if not re.fullmatch(r"[A-Za-z0-9_-]+", path.stem):
            raise ValueError("unsafe capture name")
        return meta

    scans = []
    for meta_path in sorted(cap_dir.glob("scan_*.json")):
        meta = metadata(meta_path)
        stem = meta_path.stem
        entries = meta.get("blobs")
        if not isinstance(entries, list) or len(entries) != 3 or any(
                not isinstance(b, dict) for b in entries):
            raise ValueError(f"{stem}: requires three blob entries")
        if sorted(b.get("label", "") for b in entries) != sorted(ROLES):
            raise ValueError(f"{stem}: missing or duplicate roles")
        frames = {}
        for b in entries:
            name = b.get("file")
            if not isinstance(name, str) or not name or Path(name).name != name:
                raise ValueError(f"{stem}: blob file must be a local filename")
            path = (cap_dir / name).resolve()
            if path.parent != cap_dir.resolve():
                raise ValueError(f"{stem}: blob outside capture directory")
            frames[b["label"]] = path.read_bytes()
        raw_path = cap_dir / f"{stem}_raw.bin"
        raw_match = None
        if raw_path.exists():
            raw_frames = split_usb_stream(raw_path.read_bytes())
            raw_match = raw_frames == [frames[role] for role in ROLES]
            if not raw_match:
                raise ValueError(f"{stem}: split frames differ from {raw_path.name}")
        _check(stem, frames)
        scans.append({"scan_id": stem.replace("scan_", "fw151-scan-"), "ts": meta["time"],
                      "source": stem, "frames": frames, "raw_stream_match": raw_match})
    for meta_path in sorted(cap_dir.glob("multiscan_*.json")):
        meta = metadata(meta_path)
        stem = meta_path.stem
        if type(meta.get("count")) is not int or meta["count"] <= 0:
            raise ValueError(f"{stem}: count must be a positive integer")
        for k in range(meta["count"]):
            frames = {role: (cap_dir / f"{stem}_s{k}_{role}.bin").read_bytes() for role in ROLES}
            _check(f"{stem}_s{k}", frames)
            scans.append({"scan_id": f"fw151-{stem}-s{k}", "ts": meta["time"], "source": f"{stem}_s{k}",
                          "frames": frames, "raw_stream_match": None})
    if not scans:
        raise ValueError("no captures found")
    if len({s["scan_id"] for s in scans}) != len(scans):
        raise ValueError("duplicate scan identifiers")
    words = {s["scan_id"]: {role: struct.unpack_from("<II", s["frames"][role], 0) for role in ROLES}
             for s in scans}
    second_words = [w[role][1] for w in words.values() for role in ROLES]
    return {"scans": scans, "words": words,
            "word0_all_zero": all(w[role][0] == 0 for w in words.values() for role in ROLES),
            "word1_unique": len(set(second_words)) == len(second_words)}


def _white_section(args, device):
    if not args.white:
        raise ValueError("--run requires --white; unknown-target scans are not calibration")
    cal = store.load_scan(args.white)
    identity = cal.get("device") or {}
    if str(identity.get("device_id", "")).upper() != device["device_id"]:
        raise ValueError("white reference is from another device_id")
    if identity.get("i2s_tag_config") != device["i2s_tag_config"]:
        raise ValueError("white reference i2s tag mismatch")
    if cal["meta"].get("schema") != "scio-wr/2":
        raise ValueError("white reference must use scio-wr/2")
    _check("white reference", {role: cal["blobs"].get(ROLE_WHITE[role], b"") for role in ROLES})
    return session._white_section(cal, portable_path(args.white))


def _device(args):
    if not isinstance(args.device_id, str) or not re.fullmatch(r"[0-9a-fA-F]{16}", args.device_id):
        raise ValueError("--run requires a verified 16-hex-digit --device-id")
    if not isinstance(args.i2s, str) or not args.i2s.strip():
        raise ValueError("--run requires an explicit verified --i2s tag")
    return {"device_id": args.device_id.upper(), "i2s_tag_config": args.i2s,
            "firmware_version": 151}


def _promote(rec, resp, wl, refl, payload):
    from ingest_fw138_batches import _spectrum_doc
    scans, spectra = Path(session.SCANS_DIR), Path(session.PROCESSED_DIR)
    canon = scans / session.record_filename(rec)
    spec = spectra / (canon.stem + "_spectrum.json")
    # Refuse collisions in either store before adding a canonical record.
    if canon.exists() or spec.exists():
        raise FileExistsError("record or spectrum destination already exists")
    raw_text = json.dumps(rec, indent=1, allow_nan=False)
    spec_text = json.dumps(_spectrum_doc(rec, canon, resp, wl, refl, payload),
                           indent=1, allow_nan=False)
    scans.mkdir(parents=True, exist_ok=True)
    spectra.mkdir(parents=True, exist_ok=True)
    with canon.open("x", encoding="utf-8") as f:
        f.write(raw_text)
    with spec.open("x", encoding="utf-8") as f:
        f.write(spec_text)
    return {"record": portable_path(canon), "spectrum": portable_path(spec)}


def run(parsed, args, out: Path):
    device = _device(args)
    white = _white_section(args, device)
    jobs = parsed["scans"]
    r.write_new(out / "run_plan.json", {"planned": len(jobs), "live": args.live, "i2s": args.i2s,
                                        "white": white["source"]})
    if not args.live:
        print(json.dumps({"dry_run": True, "planned": len(jobs)}))
        return
    results, last = [], 0.0
    for s in jobs:
        if last:
            time.sleep(max(0.0, 20.0 - (time.monotonic() - last)))
        rec = session.build_record(
            session.annotate(f"fw151 {s['scan_id']}", s["scan_id"], "contributed fw-151 capture"),
            device, {ROLE_SCAN[role]: s["frames"][role] for role in ROLES}, white,
            sampled_at=s["ts"], transport="usb",
            provenance={"source": "contributed unit, fw-151", "capture": s["source"], "capture_ts": s["ts"],
                        "notes": ["target unknown", "capture time has no recorded timezone"]})
        payload = session.to_payload(rec)
        status, err, promoted = None, None, None
        try:
            resp = cloud.analyze_scan(credentials.get_token(), payload)
            status = 200
            if not isinstance(resp, dict) or not isinstance(resp.get("spectrum"), list):
                raise ValueError("spectrum must be an array")
            wl, refl = cloud.spectrum_from_response(resp)
            if (len(refl) != 331 or len(wl) != 331 or not np.isfinite(refl).all()
                    or not np.isfinite(wl).all() or not (np.diff(wl) > 0).all()):
                raise ValueError("expected 331 finite bands with increasing wavelengths")
            promoted = _promote(rec, resp, wl, refl, payload)
        except cloud.CloudError as exc:
            err = str(exc)
            status = int(m.group(1)) if (m := re.search(r"HTTP (\d+)", err)) else 0
        except (ValueError, TypeError, KeyError, AttributeError, OSError) as exc:
            err = f"{type(exc).__name__}: {exc}"
        last = time.monotonic()
        results.append({"job": s["scan_id"], "status": status, "promoted": promoted, "error": err})
        print(s["scan_id"], status, "OK" if promoted else err, flush=True)
        if err:     # stop on request, validation, or persistence failure
            break
    r.write_new(out / "run_summary.json", {"submitted": len(results),
                                           "promoted": sum(1 for x in results if x["promoted"]),
                                           "results": results})


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--output", type=Path, required=True, help="new run dir under dev/")
    p.add_argument("--run", action="store_true")
    p.add_argument("--live", action="store_true")
    p.add_argument("--device-id")
    p.add_argument("--i2s", help="verified contributor processing tag; no inferred default")
    p.add_argument("--white", type=Path, help="scio-wr/2 white reference of the same device")
    a = p.parse_args()
    out = a.output.resolve()
    if not out.is_relative_to(r.DEV):
        raise ValueError("output dir must be under dev/")
    if out.exists():
        raise FileExistsError("choose a new output directory")
    if a.live and not a.run:
        p.error("--live requires --run")
    if a.run:
        device = _device(a)
        _white_section(a, device)
    parsed = parse_captures()
    r.write_new(out / "parsed.json", {
        "n_scans": len(parsed["scans"]), "word0_all_zero": parsed["word0_all_zero"],
        "word1_unique": parsed["word1_unique"],
        "scans": [{"scan_id": s["scan_id"], "ts": s["ts"], "source": s["source"],
                   "sizes": {k: len(v) for k, v in s["frames"].items()},
                   "sha256": {k: r.sha(v) for k, v in s["frames"].items()},
                   "raw_stream_match": s["raw_stream_match"]} for s in parsed["scans"]]})
    print("parsed", len(parsed["scans"]), "scans; word0 all zero:", parsed["word0_all_zero"],
          "; second header words unique:", parsed["word1_unique"])
    if a.run:
        if not a.device_id:
            raise SystemExit("--run needs --device-id (the contributor's); it cannot be guessed")
        run(parsed, a, out)


if __name__ == "__main__":
    main()
