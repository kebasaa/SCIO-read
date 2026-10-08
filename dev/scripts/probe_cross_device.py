"""Cross-device statistical-invariant comparison of scan bodies (offline).

Is the body's statistical fingerprint the same across devices and generations (-> one global
algorithm, consistent with a shared key + device_id tweak) or divergent (-> per-device/
per-generation processing)? Reuses `gradient.role_stats` for the fingerprint. Does not break
encryption; it constrains the key-architecture question and whether a single decode model could
ever generalise.

    python dev/scripts/probe_cross_device.py --output dev/analysis_output/<new-run>/cross_device.json
"""
import argparse
import base64
import json
from collections import defaultdict
from pathlib import Path

import numpy as np

import _bootstrap  # noqa: F401
from scio_offline import gradient as g
from scio_offline import research as r

FOREIGN_DIR = r.DEV / "analysis_output" / "foreign_scans"
CONTRIB = r.DEV / "analysis_output" / "foreign_fw138_20261008" / "scans.json"


def _collect():
    """device_id -> {'tag', 'provenance', 'sample': [blobs], 'sample_dark': [blobs]}."""
    devs = defaultdict(lambda: {"tag": None, "provenance": None, "sample": [], "sample_dark": []})
    for row in r.contexts():                       # owner (fw-147) + the contributor skin pair
        d = row["device"].get("device_id")
        devs[d]["tag"] = row["device"].get("i2s_tag_config")
        devs[d]["provenance"] = "owned unit (paired corpus)"
        for role in ("sample", "sample_dark"):
            if role in row["blobs"]:
                devs[d][role].append(row["blobs"][role])
    scans = json.loads(CONTRIB.read_text())         # the contributor pine/tomato/white bodies (valid)
    for s in scans["samples"]:
        for role in ("sample", "sample_dark"):
            devs[scans["device_id"]][role].append(base64.b64decode(s["blobs_b64"][role]))
        devs[scans["device_id"]]["provenance"] = "contributed fw-138 unit"
        devs[scans["device_id"]]["tag"] = scans["i2s_tag_config"]
    for path in sorted(FOREIGN_DIR.glob("*.json")):  # 5 app-embedded foreign-mock devices
        d = json.loads(path.read_text())
        dev = d["device_id"]
        for role in ("sample", "sample_dark"):
            if role in d.get("blobs_b64", {}):
                devs[dev][role].append(base64.b64decode(d["blobs_b64"][role]))
        devs[dev]["tag"] = d.get("i2s_tag_config")
        devs[dev]["provenance"] = "app-embedded mock (uncertain identity)"
    return devs


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    if a.output.exists():
        raise FileExistsError(a.output)

    devs = _collect()
    per_device = {}
    for dev, info in devs.items():
        blobs = [b for b in info["sample"] if len(b) == 1800]   # fingerprint on the sample role
        if not blobs:
            continue
        stats = g.role_stats(blobs)
        per_device[dev] = {"tag": info["tag"], "provenance": info["provenance"],
                           "n_sample": len(blobs), **stats}

    keys = ("entropy_mean", "pooled_chi_square", "max_abs_position_z", "bit_one_fraction")
    spreads = {}
    for k in keys:
        vals = [v[k] for v in per_device.values()]
        spreads[k] = {"min": float(np.min(vals)), "max": float(np.max(vals)),
                      "spread": float(np.max(vals) - np.min(vals))}
    # every device flat (chi-square near df=255), ~7.89 bits, no 4-sigma positions, bits ~0.5
    consistent = (spreads["entropy_mean"]["spread"] < 0.05
                  and all(v["positions_beyond_4_sigma"] == 0 for v in per_device.values())
                  and spreads["bit_one_fraction"]["max"] < 0.51
                  and spreads["bit_one_fraction"]["min"] > 0.49)
    report = {
        "schema": "scio-cross-device/1",
        "question": "Is the body fingerprint the same across devices/generations?",
        "devices": len(per_device),
        "per_device": per_device,
        "spreads": spreads,
        "fingerprint_consistent": bool(consistent),
        "interpretation": (
            "All devices/generations share the same random-like body fingerprint (flat byte "
            "histogram, ~7.89 bits/byte, no >4-sigma positions, bit fraction ~0.5). Consistent "
            "with one global algorithm (a shared key with device_id as a tweak), but it does not "
            "prove a shared key and does not break encryption."
            if consistent else
            "Body fingerprints differ across devices/generations; per-device or per-generation "
            "processing is indicated. See per_device."),
        "limits": [
            "Mock devices have uncertain identity/calibration; they inform, not drive.",
            "A shared fingerprint is necessary but not sufficient for a shared decode model; "
            "the supervised leakage test already found no owner-side fixed-position information.",
        ],
    }
    r.write_new(a.output, report)
    print("devices:", report["devices"], "consistent:", report["fingerprint_consistent"])
    for dev, v in per_device.items():
        print(f"  {dev} [{v['tag']}] n={v['n_sample']} ent={v['entropy_mean']:.3f} "
              f"chi2={v['pooled_chi_square']:.0f} bit1={v['bit_one_fraction']:.4f} "
              f">4sig={v['positions_beyond_4_sigma']}")


if __name__ == "__main__":
    main()
