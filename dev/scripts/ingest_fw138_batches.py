"""Ingest Vitaly's fw-138 fixed-target batches (cap/wood, 2 sessions each).

Input: the four e-mailed batch files under ``email/`` - 4 x 25 scans, two targets
(the device's own closed cap = bright, a wood block = dark), each in two independent
sessions. Each scan is three frames in wire order dark/sample/gradient (base64 of the
full blob incl. 8-byte header; 1800/1800/1416 B); one TEMP_BEFORE/TEMP_AFTER per file.

This script, in order of the flags:

  (default, no server)   parse + validate all four files and report counts/sizes.
  --white-refs           store every CAP scan as a raw ``scio-wr/2`` white reference
                         for the fw-138 device (dark/sample/gradient -> white slots).
                         Append-only into 01_rawdata/scan_json_calibration/.
  --run [--live]         build a ``scio-scan/2`` record for every scan (cap + wood),
                         reusing the EXISTING pinned fw-138 white
                         (01_rawdata/scan_json_calibration/20261008_1537_calibration.json),
                         replay each on the server (20 s spacing, --live), and PROMOTE
                         only the successes (HTTP 200 + 331 finite bands) into
                         01_rawdata/scans/ + 02_processed_data/. Failures stay in the
                         staging run dir and are never written to 01_rawdata/.

    python dev/scripts/ingest_fw138_batches.py --output dev/analysis_output/<run>
    python dev/scripts/ingest_fw138_batches.py --output dev/analysis_output/<run> --white-refs
    python dev/scripts/ingest_fw138_batches.py --output dev/analysis_output/<run> --run --live
"""
import argparse
import base64
import json
import re
import time
from pathlib import Path

import _bootstrap  # noqa: F401
import numpy as np
from scio import cloud, credentials, session, store
from scio.paths import portable_path
from scio.protocol import parse_temperature
from scio_offline import research as r

BATCHES = [  # (filename, target, session_label)
    ("scio_fw138_batch.txt", "cap", "s1"),
    ("scio_fw138_batch_cap2.txt", "cap", "s2"),
    ("scio_fw138_batch_wood.txt", "wood", "s1"),
    ("scio_fw138_batch_wood2.txt", "wood", "s2"),
]
EMAIL_DIR = r.ROOT / "email"
DEVICE_JSON = r.DEV / "analysis_output" / "foreign_fw138_20261008" / "device.json"
PINNED_WHITE = r.ROOT / "01_rawdata" / "scan_json_calibration" / "20261008_1537_calibration.json"
EXPECT_SIZES = {"dark": 1800, "sample": 1800, "gradient": 1416}
ROLE_SCAN = {"dark": "sample_dark", "sample": "sample", "gradient": "sample_gradient"}
ROLE_WHITE = {"dark": "sample_white_dark", "sample": "sample_white", "gradient": "sample_white_gradient"}
_FRAME = re.compile(r"^\s+(dark|sample|gradient)\s+word0=(\S+)\s+word1=(\S+)\s+len=(\d+)\s+b64=(\S+)\s*$")


def _temp(hexstr):
    try:
        return parse_temperature(bytes.fromhex(hexstr.strip()))
    except Exception:
        return {"raw_hex": hexstr.strip()}


def parse_batch(path: Path) -> dict:
    """Return {header, temp_before, temp_after, scans:[{idx, ts, frames{role:bytes}, words{role:(w0,w1)}}]}."""
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    out = {"file": path.name, "temp_before": None, "temp_after": None, "scans": []}
    cur = None
    for ln in lines:
        if ln.startswith("TEMP_BEFORE"):
            out["temp_before"] = _temp(ln.split(maxsplit=1)[1])
            continue
        if ln.startswith("TEMP_AFTER"):
            out["temp_after"] = _temp(ln.split(maxsplit=1)[1])
            continue
        if ln.startswith("SCAN "):
            m = re.match(r"^SCAN\s+(\d+)\s+ts=(\S+)", ln)
            cur = {"idx": int(m.group(1)) if m else len(out["scans"]) + 1,
                   "ts": m.group(2) if m else None, "frames": {}, "words": {}}
            out["scans"].append(cur)
            continue
        m = _FRAME.match(ln)
        if m and cur is not None:
            role, w0, w1, length, b64 = m.groups()
            raw = base64.b64decode(b64)
            if len(raw) != int(length) or len(raw) != EXPECT_SIZES[role]:
                raise ValueError(f"{path.name} scan {cur['idx']} {role}: size {len(raw)} "
                                 f"!= len={length}/expected={EXPECT_SIZES[role]}")
            cur["frames"][role] = raw
            cur["words"][role] = (w0, w1)
    for s in out["scans"]:
        miss = set(EXPECT_SIZES) - set(s["frames"])
        if miss:
            raise ValueError(f"{path.name} scan {s['idx']} missing frames {miss}")
    return out


def device_specs() -> dict:
    d = json.loads(DEVICE_JSON.read_text())["device"]
    return dict(d)


def parse_all(limit=None):
    batches = []
    for fname, target, sess in BATCHES:
        b = parse_batch(EMAIL_DIR / fname)
        b.update(target=target, session=sess)
        if limit:
            b["scans"] = b["scans"][:limit]
        batches.append(b)
    return batches


# ---------------------------------------------------------------- white refs
def store_cap_white_refs(batches, device, out_run: Path, wr_dir=None):
    wr_dir = wr_dir or store.WR_DIR
    manifest = []
    for b in batches:
        if b["target"] != "cap":
            continue
        for s in b["scans"]:
            blobs = {ROLE_WHITE[role]: s["frames"][role] for role in EXPECT_SIZES}
            path = store.save_calibration(blobs, device,
                                          temp_before=b["temp_before"] or {},
                                          temp_after=b["temp_after"] or {}, transport="usb")
            manifest.append({"file": portable_path(path), "target": "cap",
                             "session": b["session"], "scan_idx": s["idx"], "ts": s["ts"]})
    r.write_new(out_run / "cap_white_refs.json",
                {"count": len(manifest), "device_id": device["device_id"], "records": manifest})
    return manifest


# ---------------------------------------------------------------- run / replay
def _build_record(device, white_section, b, s):
    name = f"fw138 batch {b['target']} {b['session']} #{s['idx']:02d}"
    scan_id = f"fw138-{b['target']}-{b['session']}-{s['idx']:02d}"
    blobs = {ROLE_SCAN[role]: s["frames"][role] for role in EXPECT_SIZES}
    return session.build_record(
        session.annotate(name, scan_id, "contributed fw-138 fixed-target batch"),
        device, blobs, white_section,
        temperature={"scan_before": b["temp_before"] or {}, "scan_after": b["temp_after"] or {},
                     "note": "batch-level temperature (before/after the whole session), not per-scan"},
        status_word=0,
        calibration={"status_at_scan": "NO_NEED", "thresholds": None,
                     "thresholds_source": "not applicable (contributed unit)", "report": None},
        transport="usb",
        provenance={"source": "contributed second unit, fw-138 (Vitaly)",
                    "target": b["target"], "session": b["session"], "scan_index": s["idx"],
                    "batch_file": b["file"], "capture_ts": s["ts"],
                    "notes": ["fixed-target batch (closed cap = bright, wood = dark), 2 sessions each",
                              "paired with the existing fw-138 white 20261008_1537_calibration.json",
                              "timestamps are the contributor's capture ts; ingestion reused the pinned white"]})


def _spectrum_doc(rec, canon_path, resp, wl, refl, payload):
    return {
        "schema": session.PROCESSED_SCHEMA, "processed_at": store.now_iso(),
        "source_record": portable_path(canon_path), "scan_uid": rec.get("scan_uid"),
        "annotation": rec.get("annotation"),
        "location": {"mobile_GPS": rec.get("mobile_GPS"), "location_meta": rec.get("location_meta"),
                     "sent_to_server": "mobile_GPS" in payload},
        "spectrum": {"wavelength_nm": wl, "reflectance": refl, "n_points": len(refl),
                     "range_nm": [wl[0], wl[-1]] if wl else None},
        "server": {"endpoint": cloud.SPECTRO_URL,
                   "request_meta": {k: v for k, v in payload.items() if not k.startswith("sample")},
                   "response_meta": {k: v for k, v in resp.items() if k != "spectrum"}},
        "scan": rec}


def run(batches, device, out_run: Path, live: bool, pause: float = 20.0):
    cal = store.load_scan(PINNED_WHITE)
    if (cal.get("device") or {}).get("device_id") != device["device_id"]:
        raise ValueError("pinned white device_id mismatch")
    white_section = session._white_section(cal, portable_path(PINNED_WHITE))

    jobs = [(b, s) for b in batches for s in b["scans"]]
    plan = {"planned": len(jobs), "min_gap_seconds": pause, "live": live,
            "pinned_white": portable_path(PINNED_WHITE),
            "targets": {t: sum(len(b["scans"]) for b in batches if b["target"] == t) for t in ("cap", "wood")}}
    r.write_new(out_run / "run_plan.json", plan)
    if not live:
        print(json.dumps({"dry_run": True, **plan}))
        return

    def _already(scan_id):
        return next(Path(session.SCANS_DIR).glob(f"*{scan_id}.json"), None) is not None

    token = credentials.get_token
    results = []
    last = 0.0
    for i, (b, s) in enumerate(jobs):
        rec = _build_record(device, white_section, b, s)
        sid = rec["annotation"]["scan_id"]
        if _already(sid):   # resumable: never submit or duplicate an already-ingested scan
            results.append({"job": sid, "status": "skip", "promoted": None, "error": "already ingested"})
            print(i + 1, len(jobs), sid, "skip (already ingested)", flush=True)
            continue
        payload = session.to_payload(rec)
        if last and i:
            time.sleep(max(0.0, pause - (time.monotonic() - last)))
        status, err, promoted = None, None, None
        try:
            resp = cloud.analyze_scan(token(), payload)
            wl, refl = cloud.spectrum_from_response(resp)
            status = 200
            ok = len(refl) == 331 and bool(np.isfinite(refl).all())
            if ok:
                canon = session.write_record(rec, out_dir=session.SCANS_DIR)
                doc = _spectrum_doc(rec, canon, resp, wl, refl, payload)
                spec_path = Path(session.PROCESSED_DIR) / (canon.stem + "_spectrum.json")
                Path(session.PROCESSED_DIR).mkdir(parents=True, exist_ok=True)
                spec_path.write_text(json.dumps(doc, indent=1), encoding="utf-8")
                promoted = {"record": portable_path(canon), "spectrum": portable_path(spec_path)}
            else:
                err = f"non-331/non-finite spectrum (n={len(refl)})"
        except cloud.CloudError as exc:
            err = str(exc)
            status = int(m.group(1)) if (m := re.search(r"HTTP (\d+)", err)) else 0
        last = time.monotonic()
        row = {"job": f"{b['target']}-{b['session']}-{s['idx']:02d}", "status": status,
               "promoted": promoted, "error": err}
        results.append(row)
        print(i + 1, len(jobs), row["job"], status, "OK" if promoted else (err or ""), flush=True)
        # Fail fast on auth / rate-limit so we do not hammer the server.
        if status in (401, 403, 429):
            r.write_new(out_run / "halt.json", {"reason": "auth or rate limit", "at": row["job"]})
            break

    ok = [x for x in results if x["promoted"]]
    by = {}
    for x in results:
        key = x["job"].rsplit("-", 1)[0]
        by.setdefault(key, {"ok": 0, "fail": 0})
        by[key]["ok" if x["promoted"] else "fail"] += 1
    r.write_new(out_run / "run_summary.json",
                {"submitted": len(results), "promoted": len(ok),
                 "failed": len(results) - len(ok), "by_group": by, "results": results})
    print(json.dumps({"submitted": len(results), "promoted": len(ok), "by_group": by}))


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--output", type=Path, required=True, help="new run dir under dev/")
    p.add_argument("--white-refs", action="store_true", help="store cap scans as raw white references")
    p.add_argument("--run", action="store_true", help="build + replay + promote the samples")
    p.add_argument("--live", action="store_true", help="actually send server requests")
    p.add_argument("--limit", type=int, default=None, help="cap scans per batch (testing)")
    a = p.parse_args()
    out = a.output.resolve()
    if not out.is_relative_to(r.DEV):
        raise ValueError("output dir must be under dev/")
    out.mkdir(parents=True, exist_ok=True)

    device = device_specs()
    batches = parse_all(limit=a.limit)
    counts = {f"{b['target']}_{b['session']}": len(b["scans"]) for b in batches}
    r.write_new(out / "parsed.json",
                {"device_id": device["device_id"], "i2s": device["i2s_tag_config"],
                 "firmware": device["firmware_version"], "counts": counts,
                 "total_scans": sum(counts.values())})
    print("parsed:", json.dumps(counts), "total", sum(counts.values()))

    if a.white_refs:
        man = store_cap_white_refs(batches, device, out)
        print(f"stored {len(man)} cap white-reference records")
    if a.run:
        run(batches, device, out, live=a.live)


if __name__ == "__main__":
    main()
