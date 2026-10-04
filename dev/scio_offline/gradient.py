"""Is the gradient blob less protected or more structured than sample/dark?

The server accepts gradient edits, omission and zero-fill with an unchanged
spectrum, its first header word is a constant 110, and its body length changes
with the generation (1648 B on `-e`, 1408 B on `-o`) while the sample's does not.
If the gradient were plaintext, lightly obfuscated, or derived from the sample
body, these statistics would differ from the sample/dark ones:

* entropy, flat-histogram chi-square, per-position mean deviation,
  longest constant run and repeated 16-byte blocks;
* bit distance between the gradient and the sample/dark body of the *same* scan
  versus other scans (a derived or shared-keystream gradient would sit closer);
* the supervised leakage test of :mod:`scio_offline.leakage`.
"""
from __future__ import annotations

import math
import struct

import numpy as np

HEADER = 8
UNIFORM_SD = math.sqrt((256 ** 2 - 1) / 12)


def entropy(data: bytes) -> float:
    counts = np.bincount(np.frombuffer(data, np.uint8), minlength=256)
    p = counts[counts > 0] / len(data)
    return float(-(p * np.log2(p)).sum())


def longest_run(data: bytes) -> int:
    best = run = 1
    for a, b in zip(data, data[1:]):
        run = run + 1 if a == b else 1
        best = max(best, run)
    return best if data else 0


def bit_distance(a: bytes, b: bytes) -> float:
    n = min(len(a), len(b))
    x = np.frombuffer(a[:n], np.uint8) ^ np.frombuffer(b[:n], np.uint8)
    return float(np.unpackbits(x).mean())


def role_stats(blobs: list[bytes]) -> dict:
    """Corpus statistics for one role, over the body after the 8-byte header."""
    bodies = [b[HEADER:] for b in blobs]
    lengths = sorted({len(b) for b in bodies})
    if len(lengths) != 1:
        raise ValueError(f"mixed body lengths {lengths}")
    M = np.vstack([np.frombuffer(b, np.uint8) for b in bodies]).astype(float)
    pooled = np.bincount(M.astype(np.uint8).ravel(), minlength=256)
    expected = pooled.sum() / 256
    position_z = (M.mean(0) - 127.5) / (UNIFORM_SD / math.sqrt(M.shape[0]))
    blocks = [b[i:i + 16] for b in bodies for i in range(0, len(b) - 15, 16)]
    words = [struct.unpack_from("<II", b, 0) for b in blobs]
    return {
        "n": len(blobs), "body_bytes": lengths[0],
        "header_word0_values": sorted({w[0] for w in words}),
        "header_word1_unique": len({w[1] for w in words}),
        "entropy_mean": float(np.mean([entropy(b) for b in bodies])),
        "entropy_min": float(np.min([entropy(b) for b in bodies])),
        "pooled_chi_square": float(((pooled - expected) ** 2 / expected).sum()),
        "pooled_chi_square_df": 255,
        "max_abs_position_z": float(np.abs(position_z).max()),
        "positions_beyond_4_sigma": int((np.abs(position_z) > 4).sum()),
        "bit_one_fraction": float(np.unpackbits(M.astype(np.uint8)).mean()),
        "longest_constant_run": max(longest_run(b) for b in bodies),
        "repeated_16b_blocks": len(blocks) - len(set(blocks)),
    }


def same_vs_other(a_blobs: list[bytes], b_blobs: list[bytes], seed: int = 0) -> dict:
    """Body bit distance a_i vs b_i (same scan) against a_i vs b_j (other scans)."""
    rng = np.random.default_rng(seed)
    n = len(a_blobs)
    same = [bit_distance(a_blobs[i][HEADER:], b_blobs[i][HEADER:]) for i in range(n)]
    other = []
    for i in range(n):
        j = (i + 1 + rng.integers(n - 1)) % n
        other.append(bit_distance(a_blobs[i][HEADER:], b_blobs[j][HEADER:]))
    diff = np.mean(same) - np.mean(other)
    se = math.sqrt(np.var(same, ddof=1) / n + np.var(other, ddof=1) / n)
    return {"same_scan_mean": float(np.mean(same)), "same_scan_min": float(np.min(same)),
            "other_scan_mean": float(np.mean(other)), "difference": float(diff),
            "z": float(diff / se) if se else 0.0, "random_expectation": 0.5}
