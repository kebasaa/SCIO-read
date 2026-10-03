"""Supervised leakage test of scan bodies against server spectra (offline only).

Runs the synthetic power check first and aborts if the detectors cannot see the
fixed-position codec fixture or flag its encrypted twin. Then scans every
role x view x target on the paired corpus. No device or network access; the
frozen fresh-reference blobs are excluded. The report is written once, never
overwritten.

    python dev/scripts/probe_leakage.py --output dev/analysis_output/<new-run>/leakage.json
"""
import argparse
import hashlib
from pathlib import Path

import _bootstrap  # noqa: F401
from scio_offline import leakage as L
from scio_offline import research

ROLES = ("sample", "sample_dark")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--perm", type=int, default=5000, help="permutations per real test")
    p.add_argument("--power-perm", type=int, default=500)
    p.add_argument("--seed", type=int, default=20261003)
    a = p.parse_args()
    if a.output.exists():
        raise FileExistsError(a.output)

    corpus = L.load_corpus()
    rows = corpus["rows"]
    n, body = len(rows), len(rows[0]["blobs"]["sample"]) - L.HEADER
    power = L.power_check(n, body, n_perm=a.power_perm, seed=a.seed)
    if power["smallest_detected_fields"] is None or power["cipher_false_positives"]:
        raise SystemExit(f"power check failed: {power}")

    tgt = L.targets(corpus["spectra"], corpus["wavelength_nm"])
    groups = corpus["acquisition_group"]
    results = []
    for role in ROLES:
        blobs = [r["blobs"][role] for r in rows]
        for view in L.VIEWS:
            X = L.matrix(blobs, view)
            for name, y in tgt.items():
                results.append({
                    "role": role, "view": view, "target": name,
                    "univariate": L.univariate_scan(X, y, groups, a.perm, a.seed),
                    "ridge": L.grouped_ridge(X, y, groups, n_perm=a.perm, seed=a.seed),
                })
                print(role, view, name, results[-1]["univariate"]["p_value"],
                      results[-1]["ridge"]["p_value"], flush=True)

    tests = 2 * len(results)
    p_min = min(min(r["univariate"]["p_value"], r["ridge"]["p_value"]) for r in results)
    report = {
        "schema": "scio-leakage/1",
        "question": "Do sample/dark bodies carry information about the server spectrum?",
        "device_id": corpus["device_id"],
        "n_records": n, "body_bytes": body,
        "frozen_excluded": corpus["frozen_excluded"],
        "acquisition_groups": {g: int((groups == g).sum()) for g in sorted(set(groups))},
        "input_sha256": {role: hashlib.sha256(b"".join(r["blobs"][role] for r in rows)).hexdigest()
                         for role in ROLES},
        "permutations": a.perm, "seed": a.seed,
        "permutation_scheme": "targets shuffled within acquisition groups",
        "power_check": power,
        "results": results,
        "summary": {
            "tests": tests,
            "min_p_value": p_min,
            "bonferroni_min_p": min(1.0, p_min * tests),
            "resolution": 1 / (1 + a.perm),
        },
        "limits": [
            "Detects leakage at fixed body positions only (linear in bits, bytes or u16 words).",
            "A variable-length entropy coder in a fixed container shifts later fields; only its "
            "leading bits stay position-aligned.",
            "Power is measured on synthetic fixtures, not on the real coder.",
            "A negative is consistent with encryption under a fresh nonce; it does not prove it.",
        ],
    }
    research.write_new(a.output, report)
    print("wrote", a.output, report["summary"])


if __name__ == "__main__":
    main()
