#!/usr/bin/env python
"""Exercise notebook 10's pipeline on OLDER scan data (the log_extracted fixtures).

Each fixture has the raw blobs plus the spectrum the server returned in 2021, so
this sends the raw blobs to today's server (same code path as notebook 10) and
checks the returned spectrum against the stored one. Uses cached credentials.

    python test_notebook10.py            # runs on a few fixtures, hits the server
    python test_notebook10.py --offline  # build/save records only, no network
"""

from __future__ import annotations

import base64
import glob
import json
import sys
import uuid
from pathlib import Path

import numpy as np  # noqa: E402
import _bootstrap  # noqa: F401  (sets sys.path + cwd to the repo root)

from scio import cloud, credentials, store  # noqa: E402

DATA_DIR = Path("02_processed_data/notebook10_test")
FIXTURES = sorted(glob.glob("01_rawdata/log_extracted/*/*.json"))[:2]


def fixture_to_pair(path):
    """Turn one log_extracted fixture into (scan, white, target_spectrum)."""
    raw = json.loads(Path(path).read_text())
    b64, rd = raw.get("b64_data", {}), raw.get("raw_data", {})

    def blob(key):
        if key in rd:
            return bytes.fromhex(rd[key])
        return base64.b64decode("".join(b64[key].split()))

    device = {"device_id": b64.get("device_id"),
              "i2s_tag_config": b64.get("i2s_tag_config")}
    scan = {"path": path, "device": device,
            "blobs": {k: blob(k) for k in ("sample", "sample_dark", "sample_gradient")},
            "meta": {"sampled_at": b64.get("sampled_at")}}
    white = {"path": path, "device": device,
             "blobs": {k: blob(k) for k in ("sample_white", "sample_white_dark", "sample_white_gradient")},
             "meta": {"sampled_white_at": b64.get("sampled_white_at")}}
    target = json.loads(raw["spec_data"]) if "spec_data" in raw else None
    return scan, white, target


def build_record(scan, white, annotation, resp, wl, refl, payload_meta):
    def br(b):
        return {"size": len(b), "hex": b.hex(), "b64": store.wrap_b64(b)}
    rec = {
        "schema": "scio-session/1", "annotation": annotation,
        "device": scan["device"],
        "sampled_at": scan["meta"].get("sampled_at"),
        "sampled_white_at": white["meta"].get("sampled_white_at"),
        "raw": {**{k: br(v) for k, v in scan["blobs"].items()},
                **{k: br(v) for k, v in white["blobs"].items()}},
        "request_meta": payload_meta, "response": resp,
        "spectrum": {"wavelength_nm": wl, "reflectance": refl},
    }
    return rec


def main() -> int:
    offline = "--offline" in sys.argv[1:]
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    pairs = [(p, *fixture_to_pair(p)) for p in FIXTURES]
    print(f"{len(pairs)} older fixtures; device {pairs[0][1]['device']['device_id']}\n")

    token = None
    if not offline:
        try:
            token = credentials.get_token()
        except cloud.CloudError as e:
            print(f"Login failed: {e}"); return 1
        print(f"Logged in ({len(token)} char token).\n")

    for path, scan, white, target in pairs:
        label = f"{Path(path).parent.name}/{Path(path).stem[-6:]}"
        annotation = {"name": Path(path).parent.name, "id": uuid.uuid4().hex[:12],
                      "comment": f"notebook10 test on older fixture {Path(path).name}"}
        payload = cloud.build_scan_payload(scan, white, scan["device"]["device_id"],
                                           scan["device"]["i2s_tag_config"])
        payload_meta = {k: v for k, v in payload.items() if not k.startswith("sample")}

        if offline:
            rec = build_record(scan, white, annotation, {"note": "offline"}, [], [], payload_meta)
            (DATA_DIR / f"{annotation['id']}.json").write_text(json.dumps(rec, indent=1))
            print(f"  {label:22s} record built ({len(json.dumps(rec))//1024} KB), "
                  f"6 raw blobs, annotation ok")
            continue

        try:
            resp = cloud.analyze_scan(token, payload)
            wl, refl = cloud.spectrum_from_response(resp)
        except cloud.CloudError as e:
            print(f"  {label:22s} FAILED {e}")
            if "401" in str(e) or "403" in str(e):
                print("  token expired - re-run"); break
            continue
        rec = build_record(scan, white, annotation, resp, wl, refl, payload_meta)
        out = DATA_DIR / f"{annotation['id']}.json"
        out.write_text(json.dumps(rec, indent=1))

        msg = f"  {label:22s} -> {len(refl)} pts [{min(refl):.4f},{max(refl):.4f}]"
        if target is not None and len(target) == len(refl):
            diff = float(np.max(np.abs(np.array(refl) - np.array(target))))
            corr = float(np.corrcoef(refl, target)[0, 1])
            msg += f"  vs 2021 stored: max|diff|={diff:.2e} corr={corr:.5f}"
        print(msg + f"  saved {out.name}")

    print(f"\nRecords in {DATA_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
