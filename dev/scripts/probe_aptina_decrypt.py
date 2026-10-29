"""Actually attempt an aptina-keyed AES decrypt of the fw-138 blobs.

Motivated by: (1) the server binds each blob's signature to `device_id`, which is the
aptina id byte-pair-swapped (verified: 2ee0f4607c6b5fd5 -> E02E60F46B7CD55F); (2) Vitaly's
report of a 2017 app string "256-bit key using AptinaID" (NOTE: not found in the decompiled
apps we hold - the app has no scan crypto at all - so treated as his claim, unverified here);
(3) every blob carries a unique per-blob nonce in header word1.

This builds key candidates from the fw-138 aptina and its inverted/reverse forms (raw-pad,
repeat, sha256 = the 256-bit form, md5, sha1-pad), then uses the existing
`repeatability.verify_repeatability` (AES ECB/CBC/CTR/CFB/OFB with header/word1-derived IV
schemes, scored by same-target plaintext correlation) across the 25 same-target cap and wood
scans. This detector assumes decrypted bytes have repeatable integer structure;
compressed intermediates can fail it even with the correct key and mode (see
verify_research_summary.py's known-key counterexample). A negative result is not
universal key rejection. Honest prior: word-swap/reverse/sha256 forms were already negative for the
OWNER (bounded_identity_20261004); this is the fw-138 device's own aptina with high same-target
power. Offline only; no network.

    python dev/scripts/probe_aptina_decrypt.py --output dev/analysis_output/<run> [--nblobs 15] [--controls 40]
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

import _bootstrap  # noqa: F401
import numpy as np
from scio_offline import research as r
from scio_offline.repeatability import verify_repeatability

sys.path.insert(0, str(r.DEV / "scripts"))
import ingest_fw138_batches as ib  # noqa: E402

APTINA = "2ee0f4607c6b5fd5"
DEVICE_ID = "E02E60F46B7CD55F"   # aptina, byte-pairs swapped (verified)


def _pad(b, n):
    return (b + bytes(n))[:n] if len(b) <= n else b[:n]


def _repeat(b, n):
    return (b * ((n // len(b)) + 1))[:n]


def key_candidates() -> dict:
    """{label: key_bytes} for 16/24/32-byte keys from the aptina / inverted forms."""
    srcs = {}
    for name, hexstr in (("aptina", APTINA), ("deviceid_inverted", DEVICE_ID)):
        raw = bytes.fromhex(hexstr)
        srcs[name] = raw
        srcs[name + "_rev"] = raw[::-1]
        srcs[name + "_ascii"] = hexstr.lower().encode()
        srcs[name + "_ASCII"] = hexstr.upper().encode()
    out = {}
    for name, b in srcs.items():
        out[f"{name}.sha256_32"] = hashlib.sha256(b).digest()          # the "256-bit" form
        out[f"{name}.sha256_16"] = hashlib.sha256(b).digest()[:16]
        out[f"{name}.md5_16"] = hashlib.md5(b).digest()
        out[f"{name}.sha1_20_pad24"] = _pad(hashlib.sha1(b).digest(), 24)
        if len(b) in (16, 24, 32):
            out[f"{name}.raw"] = b
        out[f"{name}.zeropad16"] = _pad(b, 16)
        out[f"{name}.zeropad32"] = _pad(b, 32)
        out[f"{name}.repeat16"] = _repeat(b, 16)
        out[f"{name}.repeat32"] = _repeat(b, 32)
    return out


def role_blobs(batches, target, role, n):
    blobs = []
    for b in batches:
        if b["target"] != target:
            continue
        for s in b["scans"]:
            blobs.append(s["frames"][role])
    return blobs[:n]


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--nblobs", type=int, default=15)
    p.add_argument("--controls", type=int, default=40)
    a = p.parse_args()
    out = a.output.resolve()
    if not out.is_relative_to(r.DEV):
        raise ValueError("output under dev/ required")
    out.mkdir(parents=True, exist_ok=True)

    batches = ib.parse_all()
    keys = key_candidates()
    rng = np.random.default_rng(0)

    results = {}
    for target in ("cap", "wood"):
        for role in ("sample", "dark", "gradient"):
            blobs = role_blobs(batches, target, role, a.nblobs)
            if len(blobs) < 3:
                continue
            cand = []
            for label, key in keys.items():
                try:
                    best = verify_repeatability(blobs, key)
                    score = float(best.get("repeatability", float("nan")))
                except Exception as exc:
                    best, score = {"error": type(exc).__name__}, float("nan")
                cand.append((label, score, best))
            # random-key control (32-byte), same scorer
            ctrl = []
            for _ in range(a.controls):
                try:
                    ctrl.append(float(verify_repeatability(blobs, bytes(rng.integers(0, 256, 32, dtype=np.uint8)))["repeatability"]))
                except Exception:
                    pass
            ctrl = [c for c in ctrl if np.isfinite(c)]
            cand_fin = [(l, s, b) for l, s, b in cand if np.isfinite(s)]
            cand_fin.sort(key=lambda x: -x[1])
            ctrl_max = max(ctrl) if ctrl else float("nan")
            ctrl_mean = float(np.mean(ctrl)) if ctrl else float("nan")
            top = cand_fin[0] if cand_fin else (None, float("nan"), {})
            key_g = f"{target}/{role}"
            results[key_g] = {
                "n_blobs": len(blobs),
                "control_mean": round(ctrl_mean, 4), "control_max": round(ctrl_max, 4),
                "best_candidate": top[0], "best_score": round(top[1], 4),
                "best_mode": {k: top[2].get(k) for k in ("mode", "iv", "view", "offset") if k in top[2]},
                "beats_control": bool(np.isfinite(top[1]) and np.isfinite(ctrl_max) and top[1] > ctrl_max + 0.1),
                "top5": [(l, round(s, 4)) for l, s, _ in cand_fin[:5]],
            }
            print(key_g, "best", top[0], round(top[1], 4), "| ctrl_max", round(ctrl_max, 4),
                  "| BEATS CONTROL" if results[key_g]["beats_control"] else "| ~control", flush=True)

    verdict = "NO KEY FOUND — no candidate beats the random-key control"
    if any(v["beats_control"] for v in results.values()):
        verdict = "CANDIDATE BEATS CONTROL — investigate before claiming a break"
    r.write_new(out / "aptina_decrypt.json", {
        "device_id": DEVICE_ID, "aptina": APTINA,
        "premises": {"aptina_to_deviceid_byte_pair_swap": "verified",
                     "app_string_256bit_aptina": "NOT found in decompiled apps (app has no scan crypto); Vitaly's claim, unverified here",
                     "word1_per_blob_nonce": "covered via header8-based IV schemes in decode.decrypt"},
        "n_key_candidates": len(keys), "controls": a.controls,
        "verdict": verdict, "results": results})
    print("VERDICT:", verdict)


if __name__ == "__main__":
    main()
