"""No-key two-time-pad / keystream-reuse test over repeat groups and across devices.

Offline. Reuse would be a real break; the accumulated avalanche evidence predicts a clean
negative. Synthetic controls prove the detector works (reuse flagged, fresh-IV not).

    python dev/scripts/probe_twotime.py --output dev/analysis_output/<new-run>/twotime.json
"""
import argparse
from collections import defaultdict
from pathlib import Path

import _bootstrap  # noqa: F401
from scio_offline import research as r
from scio_offline import twotime as T

REPEAT_ROLES = ("sample", "sample_dark")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    if a.output.exists():
        raise FileExistsError(a.output)
    rows = r.contexts()

    # --- synthetic controls: the detector must flag reuse and clear fresh IVs ---
    length = len(rows[0]["blobs"]["sample"]) - T.HEADER
    controls = {"reused_keystream": T.pair_report(T.synthetic_set(12, length, 1, reuse=True)),
                "fresh_keystream": T.pair_report(T.synthetic_set(12, length, 2, reuse=False))}
    if not controls["reused_keystream"]["reuse_suspected"] or controls["fresh_keystream"]["reuse_suspected"]:
        raise SystemExit(f"control check failed: {controls}")

    # --- repeat groups: same device + same target, >=3 bodies ---
    groups = defaultdict(list)
    for row in rows:
        name = (row["record"].get("annotation") or {}).get("name") or "?"
        dev = row["device"].get("device_id")
        tag = row["device"].get("i2s_tag_config")
        for role in REPEAT_ROLES:
            if role in row["blobs"]:
                groups[(dev, tag, name, role)].append(row["blobs"][role])
    repeat_reports = {}
    for (dev, tag, name, role), blobs in sorted(groups.items()):
        if len(blobs) >= 3:
            repeat_reports[f"{dev}|{tag}|{name}|{role}"] = {
                "report": T.pair_report([T.body(b) for b in blobs]),
                "word1": T.word1_iv_check(blobs)}

    # --- cross-device: one sample body per device, pairwise (different plaintext) ---
    per_device = {}
    for row in rows:
        per_device.setdefault(row["device"].get("device_id"), row["blobs"]["sample"])
    cross = T.pair_report([T.body(b) for b in per_device.values()]) if len(per_device) >= 2 else None

    any_reuse = any(v["report"].get("reuse_suspected") for v in repeat_reports.values())
    report = {
        "schema": "scio-twotime/1",
        "question": "Is any keystream reused (constant/derived IV) so two ciphertexts XOR to plaintext?",
        "controls": controls,
        "repeat_groups": repeat_reports,
        "cross_device_sample": cross,
        "devices": sorted(per_device),
        "reuse_found": bool(any_reuse),
        "verdict": ("KEYSTREAM REUSE FOUND - pursue two-time-pad recovery" if any_reuse else
                    "No reuse: every repeat group XORs at the random expectation; consistent with "
                    "a fresh per-blob keystream (or per-scan plaintext randomisation), not broken."),
        "limits": [
            "Only detects reuse of an identical keystream; it cannot recover a fresh-IV cipher.",
            "Repeat groups are owner-only (the second device has no same-target repeats yet).",
            "A negative is consistent with encryption; it does not prove encryption.",
        ],
    }
    r.write_new(a.output, report)
    print("reuse_found:", report["reuse_found"])
    for k, v in repeat_reports.items():
        rep = v["report"]
        print(f"  {k}: n={rep['n_bodies']} bitdist.min={rep['bit_distance']['min']:.4f} "
              f"xent.min={rep['xor_entropy_bits']['min']:.2f} reuse={rep['reuse_suspected']}")


if __name__ == "__main__":
    main()
