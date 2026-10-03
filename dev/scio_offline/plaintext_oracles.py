"""Order-independent plaintext oracles for candidate decodes.

The prior key searches scored candidates with `decode.plaintext_score`, whose smoothness and
lag-1 autocorrelation terms assume the decoded values are (a) smooth and (b) in spatial order.
If the device emits pixels in a permuted order, or the target is a featureless dark frame, that
oracle cannot fire. This module adds one that does not depend on order.

**Dark-frame lane entropy.** A dark frame is near-constant low counts (dark current + read
noise). Under the right decode, the *high* byte of each pixel is almost always the same small
value, so at least one byte-lane has very low entropy - regardless of pixel order, because
entropy is permutation-invariant. Under a wrong key the bytes are uniform (~8 bits/lane). So the
score is ``8 - min-lane-entropy``: high for a correct dark decode, ~0 for noise.

The score assumes unpacked low-count pixels. Compression or packing can defeat it.
:func:`calibrate` reports an empirical random-key distribution, NOT a familywise
false-positive guarantee. Independent confirmation is necessary but not sufficient.
"""

from __future__ import annotations

import numpy as np

from . import decode

LANE_VIEWS = ("u16le", "u16be", "u8")     # byte-lane strides a u16/u8 layout would produce


def _byte_entropy(vals: np.ndarray) -> float:
    counts = np.bincount(vals.astype(np.uint8), minlength=256).astype(float)
    p = counts[counts > 0] / counts.sum()
    return float(-(p * np.log2(p)).sum())


def dark_lane_score(plain: bytes) -> float:
    """``8 - min lane entropy`` over plausible lane strides. High = a structured dark decode."""
    a = np.frombuffer(plain, dtype=np.uint8)
    best = 8.0
    for view in LANE_VIEWS:
        if view == "u8":
            best = min(best, _byte_entropy(a))
        else:                                    # u16: even bytes = one lane, odd = the other
            best = min(best, _byte_entropy(a[0::2]), _byte_entropy(a[1::2]))
    return 8.0 - best


def screen_key(body: bytes, key: bytes, header: bytes, *, modes=None, iv_schemes=None) -> dict:
    """Best dark-lane score for one (key) over modes x iv schemes on one body."""
    best = {"score": -1.0, "mode": None, "iv": None}
    for mode in (modes or decode.MODES):
        for scheme in (iv_schemes or decode.IV_SCHEMES):
            try:
                plain = decode.decrypt(body, key, mode=mode, iv=scheme, header=header)
            except Exception:
                continue
            s = dark_lane_score(plain)
            if s > best["score"]:
                best = {"score": s, "mode": mode, "iv": scheme}
    return best


def calibrate(body: bytes, header: bytes, *, n_random: int = 400, search_size: int,
              target_false_positives: float = 0.5, seed: int = 0, **kw) -> dict:
    """Measure a 99th-percentile heuristic cutoff, not an extreme-tail bound.

    ``target_false_positives`` remains a compatibility argument, not a guarantee.
    Search multiplicity and compression prevent interpreting a miss as exclusion.
    """
    rng = np.random.default_rng(seed)
    scores = np.array([screen_key(body, bytes(rng.integers(0, 256, 16, dtype=np.uint8)),
                                  header, **kw)["score"] for _ in range(n_random)])
    # This is an empirical prescreen, NOT an estimate at 1/search_size rarity.
    # Four hundred samples cannot resolve a one-in-90,000 tail probability.
    q = 0.99
    return {"threshold": float(np.quantile(scores, q)),
            "random_mean": float(scores.mean()), "random_max": float(scores.max()),
            "n_random": n_random, "quantile": q, "search_size": search_size,
            "empirical_resolution": 1.0 / (n_random + 1),
            "familywise_false_positive_control": False,
            "limits": "Empirical heuristic only; independently confirm survivors. "
                      "Compressed plaintext need not have a low-entropy lane."}
