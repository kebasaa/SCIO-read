#!/usr/bin/env python
"""Replay every scan in this repository through the server, to learn how it treats
white references.

Question: **how does the server decide a new white reference is needed?**
The decompiled apps say it never does - the decision is client-side, using
thresholds the server merely supplies. This replays real scans whose white
references are anywhere from minutes to ~6 years old and records exactly what
the server does with each.

Each scan is sent with **its own** white reference, with a 20 s pause between
requests to be gentle on the server. Results are written as one JSON record per
scan (fully self-contained) plus a summary table.

    python replay_all_scans.py                 # all scans, 20 s apart
    python replay_all_scans.py --limit 5       # first 5 only
    python replay_all_scans.py --pause 20      # change the pause
    python replay_all_scans.py --cross         # extra: mismatched scan/WR pairs
    python replay_all_scans.py --summary       # just re-print the summary

Resumable: scans already recorded are skipped.
"""

from __future__ import annotations

import base64
import glob
import json
import sys
import time
from datetime import datetime
from pathlib import Path

import _bootstrap  # noqa: F401  (sets sys.path + cwd to the repo root)

from scio import cloud, credentials, store  # noqa: E402

OUT_DIR = Path("02_processed_data/replay_experiment")
PAUSE_DEFAULT = 20.0


def _arg(name, default=None):
    a = sys.argv[1:]
    for i, x in enumerate(a):
        if x == name and i + 1 < len(a):
            return a[i + 1]
        if x.startswith(name + "="):
            return x.split("=", 1)[1]
    return default


# --------------------------------------------------------------------------- sources
def fixture_pairs():
    """log_extracted fixtures: raw blobs + their own WR + the 2021/2020 server spectrum."""
    out = []
    for path in sorted(glob.glob("01_rawdata/log_extracted/*/*.json")):
        raw = json.loads(Path(path).read_text())
        b64, rd = raw.get("b64_data", {}), raw.get("raw_data", {})
        if not all(k in b64 or k in rd for k in ("sample", "sample_dark", "sample_white")):
            continue

        def blob(k):
            if k in rd:
                return bytes.fromhex(rd[k])
            return base64.b64decode("".join(b64[k].split()))

        device = {"device_id": b64.get("device_id"), "i2s_tag_config": b64.get("i2s_tag_config")}
        scan = {"path": path, "device": device,
                "blobs": {k: blob(k) for k in ("sample", "sample_dark", "sample_gradient") if k in rd or k in b64},
                "meta": {"sampled_at": b64.get("sampled_at")}}
        white = {"path": path, "device": device,
                 "blobs": {k: blob(k) for k in ("sample_white", "sample_white_dark", "sample_white_gradient") if k in rd or k in b64},
                 "meta": {"sampled_white_at": b64.get("sampled_white_at")}}
        target = json.loads(raw["spec_data"]) if "spec_data" in raw else None
        out.append({"id": f"fixture/{Path(path).parent.name}/{Path(path).stem[-6:]}",
                    "source": "log_extracted", "scan": scan, "white": white, "target": target})
    return out


def captured_pairs():
    """Scans we captured over USB, paired with the stored white reference."""
    out = []
    for path in sorted(glob.glob("01_rawdata/scan_json/scan_*.json")):
        try:
            sc = store.load_scan(path)
        except Exception:
            continue
        if "sample" not in sc.get("blobs", {}):
            continue
        dev_id = sc["device"].get("device_id")
        white = store.load_latest_calibration(dev_id) if dev_id else None
        if not white:
            continue
        out.append({"id": f"captured/{Path(path).stem}", "source": "scan_json",
                    "scan": sc, "white": white, "target": None})
    return out


# --------------------------------------------------------------------------- helpers
def _age_ms(later_iso, earlier_iso):
    try:
        return int((datetime.fromisoformat(later_iso) - datetime.fromisoformat(earlier_iso))
                   .total_seconds() * 1000)
    except Exception:
        return None


def _now_age_ms(iso):
    try:
        return int((datetime.now().astimezone() - datetime.fromisoformat(iso)).total_seconds() * 1000)
    except Exception:
        return None


def build_record(item, payload_meta, resp, wl, refl, error, thresholds):
    scan, white = item["scan"], item["white"]
    sampled_at = scan["meta"].get("sampled_at")
    sampled_white_at = white["meta"].get("sampled_white_at")

    def br(b):
        return {"size": len(b), "hex": b.hex(), "b64": store.wrap_b64(b)}

    return {
        "schema": "scio-replay/1",
        "id": item["id"], "source": item["source"],
        "replayed_at": store.now_iso(),
        "device": scan["device"],
        "sampled_at": sampled_at,
        "sampled_white_at": sampled_white_at,
        "calibration": {
            "wr_age_ms_at_scan": _age_ms(sampled_at, sampled_white_at),
            "wr_age_ms_now": _now_age_ms(sampled_white_at),
            "scan_age_ms_now": _now_age_ms(sampled_at),
            "thresholds": thresholds,
            "wr_temperature": store._wr_temperature(white.get("meta", {})),
            "temperature_before": white.get("meta", {}).get("temperature_before"),
            "temperature_after": white.get("meta", {}).get("temperature_after"),
        },
        "raw": {**{k: br(v) for k, v in scan["blobs"].items()},
                **{k: br(v) for k, v in white["blobs"].items()}},
        "request_meta": payload_meta,
        "response": resp,
        "error": error,
        "spectrum": {"wavelength_nm": wl, "reflectance": refl} if refl else None,
        "reference_spectrum_2021": item.get("target"),
        "unused_but_recorded": {
            "note": "Kept though unused; may be useful later.",
            "status_word": scan.get("meta", {}).get("status_word"),
            "threshold_logic_status": ("Newer app builds abandoned the time/scans/temperature "
                                        "rules; only NEVER/NO_NEED remains."),
        },
    }


def summarize():
    rows = []
    for p in sorted(OUT_DIR.glob("*.json")):
        if p.name == "SUMMARY.json":
            continue
        d = json.loads(p.read_text())
        cal = d.get("calibration", {})
        rows.append({
            "id": d["id"],
            "wr_age_at_scan_h": (cal.get("wr_age_ms_at_scan") or 0) / 3.6e6,
            "wr_age_now_days": (cal.get("wr_age_ms_now") or 0) / 8.64e7,
            "ok": d.get("error") is None and bool(d.get("spectrum")),
            "error": (d.get("error") or "")[:70],
        })
    rows.sort(key=lambda r: -r["wr_age_now_days"])
    print(f"\n{'scan':38s} {'WRage@scan(h)':>14s} {'WRage now(d)':>13s}  {'result'}")
    print("-" * 100)
    for r in rows:
        res = "OK spectrum" if r["ok"] else f"ERROR {r['error']}"
        print(f"{r['id']:38s} {r['wr_age_at_scan_h']:14.2f} {r['wr_age_now_days']:13.1f}  {res}")
    n_ok = sum(1 for r in rows if r["ok"])
    print("-" * 100)
    print(f"{len(rows)} scans replayed: {n_ok} accepted, {len(rows)-n_ok} rejected.")
    if rows and n_ok == len(rows):
        oldest = max(r["wr_age_now_days"] for r in rows)
        print(f"\nCONCLUSION: the server accepted every scan, including white references up to "
              f"{oldest:.0f} days old.\nIt does NOT decide when a new white reference is needed - "
              f"that is purely client-side policy.")
    (OUT_DIR / "SUMMARY.json").write_text(json.dumps(rows, indent=1))
    return rows


# --------------------------------------------------------------------------- main
def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    if "--summary" in sys.argv[1:]:
        summarize()
        return 0

    pause = float(_arg("--pause", PAUSE_DEFAULT))
    limit = int(_arg("--limit", 0) or 0)

    items = fixture_pairs() + captured_pairs()
    if "--cross" in sys.argv[1:]:
        fx, cap = fixture_pairs(), captured_pairs()
        if fx and cap:
            items = [
                {"id": "cross/new-scan_with_old-WR", "source": "cross",
                 "scan": cap[0]["scan"], "white": fx[0]["white"], "target": None},
                {"id": "cross/old-scan_with_new-WR", "source": "cross",
                 "scan": fx[0]["scan"], "white": cap[0]["white"], "target": None},
            ]
    if limit:
        items = items[:limit]

    todo = [it for it in items
            if not (OUT_DIR / (it["id"].replace("/", "_") + ".json")).exists()]
    print(f"{len(items)} scans total; {len(todo)} to do "
          f"({len(items)-len(todo)} already recorded). Pause {pause:.0f}s between requests.")
    if not todo:
        summarize()
        return 0
    print(f"Estimated time: ~{len(todo)*pause/60:.1f} min\n")

    # Thresholds once (they are per-device and change ~never).
    thresholds = None
    try:
        tok = credentials.get_token()
        dev_id = todo[0]["scan"]["device"].get("device_id")
        thresholds = cloud.fetch_calibration_thresholds(tok, dev_id)
        store.cache_thresholds(dev_id, thresholds)
        print(f"server thresholds: time={thresholds['time_ms']/60000:.0f} min, "
              f"scans={thresholds['scans']}, temp={thresholds['temperature']}degC "
              f"(0 or huge = rule effectively off)\n")
    except cloud.CloudError as e:
        print(f"thresholds unavailable ({e}); continuing\n")

    consecutive_4xx = 0
    for i, item in enumerate(todo, 1):
        out = OUT_DIR / (item["id"].replace("/", "_") + ".json")
        scan, white = item["scan"], item["white"]
        # The i2s tag is a per-device constant. Some captures stored it empty (the
        # BLE-ID read failed at capture time) and the server rejects an empty tag,
        # so fall back to the white reference's tag for the same device.
        i2s = scan["device"].get("i2s_tag_config") or white["device"].get("i2s_tag_config") \
            or (white.get("meta", {}).get("device") or {}).get("i2s_tag_config")
        payload = cloud.build_scan_payload(scan, white,
                                           scan["device"].get("device_id"), i2s)
        payload_meta = {k: v for k, v in payload.items() if not k.startswith("sample")}
        resp = wl = refl = None
        error = None
        try:
            token = credentials.get_token()      # fresh: tokens are short-lived
            resp = cloud.analyze_scan(token, payload)
            wl, refl = cloud.spectrum_from_response(resp)
            consecutive_4xx = 0
        except cloud.CloudError as e:
            error = str(e)
            # Only auth failures mean "stop hammering the server". A 400 is a
            # per-scan data problem: record it and keep going, it is a result.
            if "HTTP 401" in error or "HTTP 403" in error:
                consecutive_4xx += 1
            else:
                consecutive_4xx = 0

        rec = build_record(item, payload_meta, resp, wl, refl, error, thresholds)
        out.write_text(json.dumps(rec, indent=1))
        cal = rec["calibration"]
        age_d = (cal.get("wr_age_ms_now") or 0) / 8.64e7
        status = f"OK {len(refl)} pts" if refl else f"ERROR {error[:60]}"
        print(f"[{i:2d}/{len(todo)}] {item['id']:38s} WRage={age_d:6.1f}d  {status}")

        if consecutive_4xx >= 3:
            print("\nThree consecutive client errors - stopping to avoid hammering the server.")
            break
        if i < len(todo):
            time.sleep(pause)

    summarize()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
