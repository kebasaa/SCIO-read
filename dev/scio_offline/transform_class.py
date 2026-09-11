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

Entropy coding cannot do that. A Huffman, arithmetic or range coder spends bits in
proportion to the information in its input, so a dark frame and a bright one come
out different lengths. So if the body is "compressed" in the vendor's sense, the
coder must be **fixed-rate**: either lossy transform coding to a fixed bit budget,
or a fixed-width packing.

But a fixed-width packing of sensor counts would leave positional structure - the
high bits of a 12- or 16-bit pixel are far from uniform - and there is none: zero
of 1792 byte offsets deviates more than 4 sigma from uniform, and the pooled
histogram is flat at chi-square 256.9 on df 255.

What survives both constraints is a fixed-rate transform whose output is
whitened - which is what encryption is, and also what a rate-filling entropy coder
would look like. This module records that, and declines to pick.
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


def collect(scans_dir=None) -> dict:
    """Unique bodies grouped by blob role and by scene."""
    scans_dir = Path(scans_dir or store.SCANS_DIR)
    by_role, by_scene, seen = {}, {}, set()
    for p in sorted(scans_dir.glob("*.json")):
        rec = session.load_record(p)
        scene = _scene(rec)
        scan_b, white_b = session.record_blobs(rec)
        for key, blob in {**scan_b, **white_b}.items():
            body = blob[8:]
            h = hash(body)
            if h in seen:
                continue
            seen.add(h)
            by_role.setdefault(key, []).append(body)
            if key in ("sample", "sample_dark"):
                by_scene.setdefault(scene, []).append(body)
    return {"by_role": by_role, "by_scene": by_scene}


def size_invariance(by_role: dict) -> dict:
    """Does output length ever depend on content? (The decisive size argument.)"""
    out = {}
    for role, bodies in sorted(by_role.items()):
        sizes = sorted({len(b) for b in bodies})
        out[role] = {"n_bodies": len(bodies), "distinct_lengths": sizes,
                     "content_dependent": len(sizes) > 1}
    any_varies = any(v["content_dependent"] for v in out.values())
    return {
        "per_role": out,
        "length_ever_depends_on_content": any_varies,
        "implication": (
            "Variable length would be the signature of entropy coding."
            if any_varies else
            "Length is fixed per (generation, role) across every scene in the corpus. "
            "Entropy coding spends bits in proportion to input information and cannot "
            "produce a constant length for a dark frame and a bright one alike, so any "
            "compression here must be fixed-rate."),
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
            "Scene information content leaves no trace in output entropy "
            "(spread {:.4f} bits/byte). A variable-rate coder would leak it."
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
                "A container or coder table would show a head well below its entropy "
                "ceiling. Compare head_fraction_of_ceiling against ~1.0.")}


def run(scans_dir=None) -> dict:
    """Produce the verdict artifact.

    The schema deliberately cannot express "encryption ruled out". No software test
    can establish that: the device could encrypt and the server decrypt, and every
    artefact we can read sits outside that path.
    """
    data = collect(scans_dir)
    size = size_invariance(data["by_role"])
    ent = entropy_by_scene(data["by_scene"])
    head = coder_header_scan(data["by_role"])

    fixed_rate_only = not size["length_ever_depends_on_content"]
    return {
        "schema": "scio-transform-class/1",
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
                "The app ships UnsupportedCompressionConversion - you re-bin between "
                "binning tables, you do not convert between encryptions.",
                "The gradient body length changes with generation (1648 B on -e, "
                "1408 B on -o) while the sample's does not.",
            ],
            "against": [
                "A 633,600-trial sweep of eight known codecs at every byte offset 0-32 "
                "and every bit offset 0-7, keeping partial output, produced zero "
                "plausible decodes on 300 unique bodies.",
                "Output length never depends on content, so any compression must be "
                "fixed-rate - which excludes ordinary entropy coding.",
                "A fixed-width packing of sensor counts would leave positional "
                "structure; zero of 1792 offsets deviates beyond 4 sigma.",
            ],
        },
        "encryption": {
            "status": "not_excluded",
            "why_not_excludable": (
                "The device could encrypt and the server decrypt. The Android client is a "
                "verified byte-for-byte pass-through, so it would contain no crypto either "
                "way. No artefact reachable by software sits on that path."),
            "for": [
                "Fixed-length, fully whitened output with no positional structure is what "
                "encryption produces.",
            ],
            "against": [
                "No crypto primitive applied to scan data exists in any of eight "
                "decompiled app trees (weak: the client would look identical either way).",
                "The claim's original basis was a misread SharedPreferences helper, "
                "getKeyPerAptinaId.",
            ],
        },
        "note_on_avalanche": (
            "The 0.49986 bit distance between captures of an unchanged target is NOT "
            "evidence for encryption over compression. The 2.1 % spectral agreement it "
            "rests on is measured after binning ~2.7 pixels per band; per-pixel noise "
            "differs everywhere, and entropy coders avalanche on any input difference."),
        "what_would_settle_it": [
            "dsp_op (32628 B) via an external SPI-flash dump - the code itself.",
            "The four binning tables, which would fix the pixel->band geometry.",
            "SDK credentials for /v1/external_sdk/intermediate_scan, which is live "
            "(401 on POST, 405 on GET) and sits between the blob and the spectrum.",
        ],
        "conclusion": (
            "Fixed-rate, whitened, positionally featureless. That is consistent with "
            "encryption and with a rate-filling proprietary coder, and the corpus cannot "
            "separate them. Reporting either as established would overstate the evidence."),
    }


def write_report(report: dict, path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=1), encoding="utf-8")
    return path
