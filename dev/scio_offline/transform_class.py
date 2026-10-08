"""What *class* of transform is applied to the blob body?

Not "what is the key" - that question presupposes an answer. The corpus of 97
scans can say something about the class, and this module says exactly as much as
it can and no more.

The single sharpest observation available is about **size**, and it needs the
whole corpus to see. Across 97 captures of wildly different scenes - dark frames,
a white calibration box, bark, soil crust, skin, rock, a hand - the sample body is
**always exactly 1792 bytes**, the dark body always 1792, the gradient always
1648. Output length depends only on (generation, blob role). It never depends on
content.

Fixed container size does NOT imply a fixed-rate internal codec. Variable-rate
streams can be padded, stored in fixed buffers, or combined with other fields.

Finite-sample byte entropy and positional tests are diagnostics, not sufficient
to identify compression, encryption, packing, or their absence.

The older fixed-rate exclusion in this module was overstated. Historical reports
are retained; new reports use schema 2 and leave these alternatives open.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from scio import session, store

from . import decode


def _scene(rec: dict) -> str:
    """Label a record by what was in front of the sensor."""
    name = ((rec.get("annotation") or {}).get("name") or "").lower()
    if name.startswith("dark"):
        return "dark"
    if "calibrationbox" in name or "calibration" in name:
        return "calibration_box"
    if "static" in name:
        return "static_series"
    return "other"


def _generation(rec: dict) -> str:
    """Generation key: the i2s tag decides the binning/geometry (e.g. -e vs bare)."""
    return (rec.get("device") or {}).get("i2s_tag_config") or "unknown"


def collect(scans_dir=None) -> dict:
    """Unique bodies grouped by blob role (and by generation) and by scene."""
    scans_dir = Path(scans_dir or store.SCANS_DIR)
    by_role, by_role_gen, by_scene, seen = {}, {}, {}, set()
    for p in sorted(scans_dir.glob("*.json")):
        rec = session.load_record(p)
        scene = _scene(rec)
        gen = _generation(rec)
        scan_b, white_b = session.record_blobs(rec)
        for key, blob in {**scan_b, **white_b}.items():
            body = blob[8:]
            h = hash(body)
            if h in seen:
                continue
            seen.add(h)
            by_role.setdefault(key, []).append(body)
            by_role_gen.setdefault(key, {}).setdefault(gen, []).append(body)
            if key in ("sample", "sample_dark"):
                by_scene.setdefault(scene, []).append(body)
    return {"by_role": by_role, "by_role_gen": by_role_gen, "by_scene": by_scene}


def size_invariance(by_role_gen: dict) -> dict:
    """Does output length depend on content? Judged *within each generation*.

    Length legitimately differs between i2s generations (e.g. the gradient is 1648 B
    on ``-e`` and 1408 B on the bare ``20150812`` tag). The decisive question is
    whether, holding the generation fixed, a dark frame and a lit scene come out the
    same length. ``content_dependent_within_generation`` answers exactly that.
    """
    out = {}
    any_within = False
    for role, gens in sorted(by_role_gen.items()):
        per_gen, all_lengths = {}, set()
        for gen, bodies in sorted(gens.items()):
            sizes = sorted({len(b) for b in bodies})
            all_lengths |= set(sizes)
            per_gen[gen] = {"n_bodies": len(bodies), "distinct_lengths": sizes,
                            "content_dependent": len(sizes) > 1}
        within = any(v["content_dependent"] for v in per_gen.values())
        any_within |= within
        out[role] = {"by_generation": per_gen, "distinct_lengths": sorted(all_lengths),
                     "content_dependent_within_generation": within,
                     "content_dependent": within}
    return {
        "per_role": out,
        "length_ever_depends_on_content": any_within,
        "implication": (
            "Within some generation, observed length varies with content; this alone "
            "does not identify a codec."
            if any_within else
            "Observed container length is fixed within each (role, generation). Across "
            "generations it differs by design. Padding or a fixed buffer can hide "
            "variable-rate compression; this does not establish a fixed-rate codec or "
            "exclude entropy coding."),
    }


def entropy_by_scene(by_scene: dict) -> dict:
    """A dark frame carries far less information than a lit one. Does it show?"""
    out = {}
    for scene, bodies in sorted(by_scene.items()):
        ents = [decode.entropy(b) for b in bodies]
        out[scene] = {"n": len(ents), "min": float(np.min(ents)),
                      "mean": float(np.mean(ents)), "max": float(np.max(ents))}
    means = [v["mean"] for v in out.values() if v["n"] >= 2]
    spread = float(max(means) - min(means)) if len(means) > 1 else None
    return {
        "per_scene": out,
        "mean_entropy_spread": spread,
        "implication": (
                "Observed mean byte-entropy spread is {:.4f} bits/byte. "
                "This summary cannot distinguish compression from encryption."
            .format(spread) if spread is not None and spread < 0.05 else
            "Entropy varies with scene; worth investigating as a rate signal."),
    }


def coder_header_scan(by_role: dict, prefixes=(8, 16, 32, 64)) -> dict:
    """Is there a low-entropy head, as a container or coder table would leave?

    The corpus-wide positional test measured the *mean* byte per offset, which
    catches a fixed bias but not a variable-length header. This compares the
    entropy of the first N bytes against the tail.
    """
    out = {}
    for role, bodies in sorted(by_role.items()):
        if len(bodies) < 3:
            continue
        rows = {}
        for n in prefixes:
            heads = [decode.entropy(b[:n]) for b in bodies]
            tails = [decode.entropy(b[n:]) for b in bodies]
            # Short strings cannot reach full entropy; compare to the ceiling for n.
            ceiling = float(np.log2(min(n, 256)))
            rows[f"first_{n}"] = {
                "head_mean": float(np.mean(heads)),
                "head_ceiling": ceiling,
                "head_fraction_of_ceiling": float(np.mean(heads) / ceiling),
                "tail_mean": float(np.mean(tails)),
            }
        out[role] = rows
    return {"per_role": out,
            "implication": (
                "Prefix entropy is a finite-sample diagnostic, not proof of a "
                "header, table, or their absence. Small prefixes require matched controls.")}


def run(scans_dir=None) -> dict:
    """Produce the verdict artifact.

    The schema deliberately cannot express "encryption ruled out". No software test
    can establish that: the device could encrypt and the server decrypt, and every
    artefact we can read sits outside that path.
    """
    data = collect(scans_dir)
    size = size_invariance(data["by_role_gen"])
    ent = entropy_by_scene(data["by_scene"])
    head = coder_header_scan(data["by_role"])

    return {
        "schema": "scio-transform-class/2",
        "ran_at": store.now_iso(),
        "unique_bodies": sum(len(v) for v in data["by_role"].values()),
        "size_invariance": size,
        "entropy_by_scene": ent,
        "coder_header_scan": head,
        "verdict": "undetermined",
        "compression": {
            "status": "not_demonstrated",
            "for": [
                "The vendor's API calls the i2s tag compression_version; the parameter "
                "carrying it is named i2sTag in the un-obfuscated 2017 build.",
                "It travels with the four binning-table checksums.",
                "UnsupportedCompressionConversion is an app label; its meaning alone "
                "does not identify an algorithm or rule out layered encryption.",
                "The gradient body length changes with generation (1648 B on -e, "
                "1408 B on -o) while the sample's does not.",
            ],
            "against": [
                "See separately versioned codec experiments for bounded negative "
                "results; this routine does not run a codec search.",
            ],
        },
        "encryption": {
            "status": "not_excluded",
            "why_not_excludable": (
                "The device could encrypt and the server decrypt. The Android client is a "
                "pass-through in inspected Java methods. Native and firmware "
                "coverage remains incomplete; software routes are not exhausted."),
            "for": [
                "High byte entropy is consistent with encryption but also with "
                "other encodings; it is not proof of whitening.",
            ],
            "against": [
                "No connected scan cipher was identified in inspected Java methods; "
                "this does not establish absence across all supplied code.",
                "The claim's original basis was a misread SharedPreferences helper, "
                "getKeyPerAptinaId.",
            ],
        },
        "note_on_avalanche": (
            "Large bit distances between repeated captures do not by themselves "
            "distinguish encryption from compression. Pixel count and binning ratio "
            "have not been established; do not infer them from payload length."),
        "what_would_settle_it": [
            "Verified firmware implementation or code-connected decoder/calibration tables.",
            "Independently matched intermediate vectors and opaque inputs.",
        ],
        "conclusion": (
            "Measured container lengths and byte entropy do not establish the "
            "transform class. Compression-only (including padded streams), encryption, "
            "packing, and layered transformations remain unresolved."),
    }


def write_report(report: dict, path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=1), encoding="utf-8")
    return path
