"""Compare gradient blobs with sample/dark blobs, offline (HANDOVER task: gradient blob).

    python dev/scripts/probe_gradient.py --output dev/analysis_output/<new-run>/gradient.json
"""
import argparse
import hashlib
from pathlib import Path

import _bootstrap  # noqa: F401
from scio_offline import gradient as g
from scio_offline import leakage as L
from scio_offline import research

FIXTURES = research.DEV / "private/lab_1_3_12_fixtures"


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--perm", type=int, default=5000)
    p.add_argument("--seed", type=int, default=20261004)
    a = p.parse_args()
    if a.output.exists():
        raise FileExistsError(a.output)
    corpus = L.load_corpus()
    rows = corpus["rows"]
    roles = {k: [r["blobs"][k] for r in rows] for k in ("sample", "sample_dark", "sample_gradient")}
    stats = {k: g.role_stats(v) for k, v in roles.items()}
    unique_white = {}
    for k in ("sample_white", "sample_white_gradient"):
        unique_white[k] = g.role_stats(sorted({r["blobs"][k] for r in rows}))
    pairs = {
        "gradient_vs_sample": g.same_vs_other(roles["sample_gradient"], roles["sample"], a.seed),
        "gradient_vs_dark": g.same_vs_other(roles["sample_gradient"], roles["sample_dark"], a.seed),
        "sample_vs_dark": g.same_vs_other(roles["sample"], roles["sample_dark"], a.seed),
    }
    tgt = L.targets(corpus["spectra"], corpus["wavelength_nm"])
    leak = []
    for view in L.VIEWS:
        X = L.matrix(roles["sample_gradient"], view)
        for name, y in tgt.items():
            leak.append({"view": view, "target": name,
                         "univariate": L.univariate_scan(X, y, corpus["acquisition_group"], a.perm, a.seed),
                         "ridge": L.grouped_ridge(X, y, corpus["acquisition_group"], n_perm=a.perm, seed=a.seed)})
    ps = [min(x["univariate"]["p_value"], x["ridge"]["p_value"]) for x in leak]
    older = {}
    for path in sorted(FIXTURES.glob("*GRADIENT*.bin")) + sorted(FIXTURES.glob("*gradient*.bin")):
        blob = path.read_bytes()
        older[path.name] = {"bytes": len(blob), "sha256": hashlib.sha256(blob).hexdigest(),
                            "header_word0": int.from_bytes(blob[:4], "little"),
                            "body_entropy": g.entropy(blob[g.HEADER:])}
    report = {
        "schema": "scio-gradient/1",
        "device_id": corpus["device_id"], "n_records": len(rows),
        "roles": stats, "white_roles_unique": unique_white,
        "same_scan_bit_distance": pairs,
        "leakage": {"permutations": a.perm, "results": leak, "tests": 2 * len(leak),
                    "min_p_value": min(ps), "bonferroni_min_p": min(1.0, min(ps) * 2 * len(leak))},
        "older_generation_fixtures": older,
        "limits": [
            "Statistics bound plaintext/structured/derived gradients; they cannot identify an opaque coding.",
            "Leakage targets are reflectance summaries; a gradient carrying non-spectral data would not leak.",
            "Older-generation fixtures are vendor code constants of unknown capture identity.",
        ],
    }
    research.write_new(a.output, report)
    for k, v in stats.items():
        print(k, {x: v[x] for x in ("body_bytes", "header_word0_values", "entropy_mean", "pooled_chi_square",
                                    "positions_beyond_4_sigma", "longest_constant_run", "repeated_16b_blocks")})
    print(pairs)
    print("leakage min p", min(ps), "tests", 2 * len(leak))
    print(older)


if __name__ == "__main__":
    main()
