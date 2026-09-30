#!/usr/bin/env python
"""Re-screen the identifier-derived key set under the dark-frame oracle (offline).

The 2,111+ identifier/serial/version keys were already negative under the smoothness oracle. This
re-runs them under `plaintext_oracles.dark_lane_score`, which is order-independent and works on
featureless dark frames - the case the old oracle could miss. The device-binding finding makes an
identifier-derived key unlikely (the key is a device-held secret, not a public-identifier
derivation), so this is a bounded, expected-negative clean run, recorded either way.

First pass: every key x mode x IV scheme on one dark body. Calibrate the threshold on random keys
at the true search size. Escalate anything above threshold to all dark bodies, scoring the minimum
across bodies (a one-body fluke collapses). Writes dev/analysis_output/dark_rescreen.json.
"""

from __future__ import annotations

import glob
import json
import time
from pathlib import Path

import _bootstrap  # noqa: F401

from scio import session, store  # noqa: E402
from scio.paths import portable_path  # noqa: E402
from scio_offline import decode, keyrecover, plaintext_oracles as po  # noqa: E402

OUT = Path("dev/analysis_output/dark_rescreen.json")


def dark_bodies():
    bodies, seen = [], set()
    for p in sorted(glob.glob("01_rawdata/scans/*.json")):
        rec = session.load_record(p)
        s, _ = session.record_blobs(rec)
        b = s.get("sample_dark")
        if b and hash(b) not in seen:
            seen.add(hash(b))
            bodies.append(b)
    return bodies


def device_meta():
    dev = {}
    for p in glob.glob("01_rawdata/scans/*.json"):
        d = session.load_record(p).get("device") or {}
        dev.update({k: v for k, v in d.items() if v})
        dev.update({k: v for k, v in (d.get("device_info_raw") or {}).items() if v})
    return dev


def main() -> int:
    t0 = time.time()
    bodies = dark_bodies()
    header = bytes(8)                       # dark blobs: type word 0; second word is per-blob
    keys = keyrecover.candidate_keys_from_device(device_meta())
    search = len(keys) * len(decode.MODES) * len(decode.IV_SCHEMES)
    print(f"{len(keys)} keys x {len(decode.MODES)}x{len(decode.IV_SCHEMES)} = {search} combos; "
          f"{len(bodies)} dark bodies")

    cal = po.calibrate(bodies[0], header, search_size=search)
    print(f"threshold {cal['threshold']:.3f} (random mean {cal['random_mean']:.3f}, "
          f"max {cal['random_max']:.3f})")

    first, best = [], {"score": -1.0}
    for label, key in keys.items():
        r = po.screen_key(bodies[0], key, header)
        r["label"] = label
        if r["score"] > best["score"]:
            best = dict(r)
        if r["score"] >= cal["threshold"]:
            first.append((label, key, r))
    print(f"first pass done [{time.time()-t0:.0f}s]; best {best['score']:.3f} ({best.get('label')}); "
          f"{len(first)} above threshold")

    confirmed = []
    for label, key, r in first:
        scores = [po.screen_key(b, key, header, modes=[r["mode"]], iv_schemes=[r["iv"]])["score"]
                  for b in bodies]
        mn = min(scores)
        if mn >= cal["threshold"]:
            confirmed.append({"label": label, "mode": r["mode"], "iv": r["iv"],
                              "min_score": mn, "first_score": r["score"]})

    hit = bool(confirmed)
    report = {
        "schema": "scio-dark-rescreen/1", "ran_at": store.now_iso(),
        "keys": len(keys), "combos": search, "dark_bodies": len(bodies),
        "calibration": cal,
        "best_first_pass": {k: best.get(k) for k in ("label", "score", "mode", "iv")},
        "above_threshold_first_pass": len(first),
        "confirmed_across_all_bodies": confirmed,
        "verdict": "hit" if hit else "negative",
        "meaning": ("A candidate cleared the calibrated threshold on every dark body." if hit else
                    "No identifier-derived key produces a low-entropy dark decode on all bodies. "
                    "Consistent with the device-binding finding: the key is a device-held secret, "
                    "not derivable from public identifiers."),
        "elapsed_s": round(time.time() - t0, 1),
    }
    OUT.write_text(json.dumps(report, indent=1), encoding="utf-8")
    print(f"VERDICT: {report['verdict']}  [{report['elapsed_s']}s]  -> {portable_path(OUT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
