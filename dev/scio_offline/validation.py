"""Score a candidate decoder against every scan whose true spectrum we hold.

The project has always had the *bar* written down - ``pipeline.acceptance`` encodes
it - but never a way to apply it. The only comparison ever written was a
``matplotlib`` cell whose branch has never executed. So every negative result so
far rests on proxy oracles (smoothness, cross-scan correlation) rather than on the
one thing that actually settles a decode: does it reproduce the spectrum the server
returned for those exact bytes?

That is now answerable. ``02_processed_data/`` holds 92 spectra for the same blobs
in ``01_rawdata/scans/``, and 42 of those records independently carry the spectrum
the server returned in 2020/2021 for the same input. A candidate decoder either
reproduces them or it does not.

    from scio_offline import validation
    report = validation.validate(my_decoder)      # bytes... -> 331 floats
    report["passed"]                              # the documented gate

**Held out by construction.** Nothing here fits anything. A decoder is handed raw
blobs and scored on all 92 records at once, so there is no train/test split to get
wrong and no way to tune against the answer without noticing.

The gate is `pipeline.acceptance(..., kind="reference")`: median Pearson >= 0.90.
That is deliberately not a high bar for *shape* - it is a floor, not a finish line.
A real decode scores ~1.0; the 0.90 exists so a near-miss is visible rather than
silently rejected.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from scio import session, store

from . import pipeline

#: Scored records: a canonical scan plus the spectrum the server returned for it.
PROCESSED_DIR = store.PROCESSED_DIR
SCANS_DIR = store.SCANS_DIR


def load_pairs(scans_dir=SCANS_DIR, processed_dir=PROCESSED_DIR) -> list[dict]:
    """Every (blobs, true spectrum) pair available locally.

    Returns dicts with ``blobs`` (raw bytes by key), ``spectrum`` (the server's
    331 floats), ``wavelength_nm``, ``name`` and ``source``. Records without a
    processed counterpart - the five dark frames the server rejects as low signal -
    are skipped, since there is no truth to score against.
    """
    processed_dir, scans_dir = Path(processed_dir), Path(scans_dir)
    pairs = []
    for proc in sorted(processed_dir.glob("*_spectrum.json")):
        d = json.loads(proc.read_text(encoding="utf-8"))
        rec = d.get("scan")
        if not rec:
            continue
        scan_b, white_b = session.record_blobs(rec)
        spec = d.get("spectrum", {})
        refl = spec.get("reflectance")
        if not refl:
            continue
        pairs.append({
            "name": (rec.get("annotation") or {}).get("name"),
            "scan_uid": rec.get("scan_uid"),
            "source": (rec.get("provenance") or {}).get("source"),
            "blobs": {**scan_b, **white_b},
            "spectrum": np.asarray(refl, float),
            "wavelength_nm": spec.get("wavelength_nm"),
            # The 2020/21 answer, where history recorded one. Same input, same
            # server, six years apart - an independent check on the check.
            "reference_spectrum": (rec.get("reference_spectrum") or {}).get("reflectance"),
        })
    return pairs


def validate(decoder, pairs=None, *, kind: str = "reference",
             limit: int | None = None) -> dict:
    """Run *decoder* over every pair and apply the documented acceptance gate.

    ``decoder(blobs: dict[str, bytes]) -> sequence[float]`` must return one curve
    per scan. Returning ``None`` counts as a decline and is reported, not scored -
    a decoder that answers on 3 of 92 records has not decoded anything, and the
    ``answered`` count in the report is what makes that visible.
    """
    pairs = load_pairs() if pairs is None else pairs
    if limit:
        pairs = pairs[:limit]

    metrics, rows, errors, declined = [], [], 0, 0
    for p in pairs:
        try:
            out = decoder(p["blobs"])
        except Exception as exc:                     # a candidate may legitimately fail
            errors += 1
            rows.append({"name": p["name"], "error": f"{type(exc).__name__}: {exc}"[:120]})
            continue
        if out is None:
            declined += 1
            rows.append({"name": p["name"], "error": "decoder declined"})
            continue
        curve = np.asarray(out, float)
        if curve.shape != p["spectrum"].shape:
            rows.append({"name": p["name"],
                         "error": f"shape {curve.shape} != {p['spectrum'].shape}"})
            errors += 1
            continue
        m = pipeline.compare_curves(curve, p["spectrum"])
        metrics.append(m)
        rows.append({"name": p["name"], "source": p["source"],
                     "pearson_r": m["pearson_r"],
                     "spectral_angle_rad": m["spectral_angle_rad"]})

    gate = pipeline.acceptance(metrics, kind)
    rs = [m["pearson_r"] for m in metrics if np.isfinite(m["pearson_r"])]
    return {
        "schema": "scio-validation/1",
        "checked_at": store.now_iso(),
        "pairs_available": len(pairs),
        "answered": len(metrics),
        "declined": declined,
        "errors": errors,
        # A gate can only pass if the decoder actually answered on most records.
        # Otherwise a decoder that solves one lucky scan would "pass" on a median
        # of one sample.
        "passed": bool(gate["passed"] and len(metrics) >= max(3, 0.8 * len(pairs))),
        "gate": gate,
        "pearson": {
            "min": float(np.min(rs)) if rs else None,
            "median": float(np.median(rs)) if rs else None,
            "max": float(np.max(rs)) if rs else None,
        } if rs else None,
        "per_scan": rows,
    }


def write_report(report: dict, path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=1), encoding="utf-8")
    return path


# --------------------------------------------------------------------- self-checks
def perfect_decoder(pairs=None):
    """A decoder that returns the true answer - the harness must score it 1.0.

    Not a joke: a validation harness that cannot recognise a correct decode is
    worse than none, because it would reject a real result. Paired with
    :func:`noise_decoder` below, this brackets the harness from both sides.
    """
    lookup = {id(p["blobs"]): p["spectrum"] for p in (pairs or load_pairs())}

    def decode(blobs):
        return lookup.get(id(blobs))
    return decode


def noise_decoder(seed: int = 0):
    """A decoder that returns shuffled noise - the harness must reject it."""
    rng = np.random.default_rng(seed)

    def decode(blobs):
        return rng.random(331)
    return decode


def self_check(pairs=None) -> dict:
    """Bracket the harness: truth must pass, noise must fail."""
    pairs = load_pairs() if pairs is None else pairs
    good = validate(perfect_decoder(pairs), pairs)
    bad = validate(noise_decoder(), pairs)
    return {
        "pairs": len(pairs),
        "truth_passes": good["passed"],
        "truth_median_r": good["gate"]["median_pearson_r"],
        "noise_passes": bad["passed"],
        "noise_median_r": bad["gate"]["median_pearson_r"],
        "harness_ok": bool(good["passed"] and not bad["passed"]),
    }
