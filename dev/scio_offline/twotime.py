"""Two-time-pad / keystream-reuse cryptanalysis of scan bodies (no key guessed).

If the device encrypts with a stream/CTR cipher and the keystream is *reused* (a constant
or device-derived IV rather than a fresh per-blob one), then XORing two ciphertexts cancels
the keystream and leaves ``XOR(plaintext_i, plaintext_j)``. For two scans of the *same*
physical target the plaintexts are near-identical, so a reused keystream would make the two
bodies near-identical (tiny bit distance, long zero runs, low XOR entropy). A fresh per-blob
keystream (or genuine per-scan plaintext randomisation) leaves the XOR looking random
(~0.5 bit distance, full entropy).

This is the one attack that needs **no key** and could break the cipher outright. The owner's
corpus has repeat groups (``current_static`` ×30, calibration, skin) that make it testable.
``stream_hypothesis`` only tests *guessed* keystreams; this is the complementary no-key test.
"""
from __future__ import annotations

import hashlib
import math
import struct

import numpy as np

HEADER = 8


def header_words(blob: bytes) -> tuple[int, int]:
    return struct.unpack_from("<II", blob, 0)


def body(blob: bytes) -> bytes:
    return blob[HEADER:]


def _entropy(data: bytes) -> float:
    counts = np.bincount(np.frombuffer(data, np.uint8), minlength=256)
    p = counts[counts > 0] / len(data)
    return float(-(p * np.log2(p)).sum())


def _longest_zero_run(data: bytes) -> int:
    best = run = 0
    for b in data:
        run = run + 1 if b == 0 else 0
        best = max(best, run)
    return best


def pair_report(bodies: list[bytes]) -> dict:
    """Pairwise-XOR statistics over a set of same-generation bodies.

    ``reuse_suspected`` is True only if some pair's XOR looks like structured plaintext
    (small bit distance, or low XOR entropy with a long zero run) - the signature of a
    reused keystream. For encrypted bodies with fresh IVs every statistic sits at the
    random expectation.
    """
    n = len(bodies)
    if n < 2:
        return {"n_bodies": n, "n_pairs": 0, "insufficient": True}
    arr = [np.frombuffer(b, np.uint8) for b in bodies]
    length = len(arr[0])
    bitdist, xent, zrun, zfrac = [], [], [], []
    min_bits = 1.0
    for i in range(n):
        for j in range(i + 1, n):
            x = np.bitwise_xor(arr[i], arr[j])
            bd = float(np.unpackbits(x).mean())
            bitdist.append(bd)
            min_bits = min(min_bits, bd)
            xb = x.tobytes()
            xent.append(_entropy(xb))
            zrun.append(_longest_zero_run(xb))
            zfrac.append(float((x == 0).mean()))
    # random expectation: bit distance 0.5, XOR entropy ~8, zero-byte fraction 1/256,
    # longest zero run ~ log_256(length).
    random_zrun = math.log(length, 256)
    reuse = (min_bits < 0.10) or (min(xent) < 7.0 and max(zrun) > 8 * random_zrun)
    return {
        "n_bodies": n, "n_pairs": len(bitdist), "body_bytes": length,
        "bit_distance": {"mean": float(np.mean(bitdist)), "min": min_bits, "max": float(np.max(bitdist))},
        "xor_entropy_bits": {"mean": float(np.mean(xent)), "min": float(np.min(xent))},
        "zero_byte_fraction_max": float(np.max(zfrac)),
        "longest_zero_run_max": int(np.max(zrun)),
        "random_longest_zero_run": round(random_zrun, 2),
        "reuse_suspected": bool(reuse),
    }


def word1_iv_check(blobs: list[bytes]) -> dict:
    """Is the second header word an IV with exploitable structure?

    Reports whether any word1 repeats (a direct keystream-reuse opening) and whether bodies
    whose word1 are numerically close are any more similar than random (a weak-PRNG tell).
    """
    words = [header_words(b)[1] for b in blobs]
    bodies = [np.frombuffer(body(b), np.uint8) for b in blobs]
    n = len(blobs)
    dups = len(words) - len(set(words))
    dw, bd = [], []
    for i in range(n):
        for j in range(i + 1, n):
            dw.append(abs(words[i] - words[j]))
            bd.append(float(np.unpackbits(np.bitwise_xor(bodies[i], bodies[j])).mean()))
    corr = float(np.corrcoef(dw, bd)[0, 1]) if len(dw) > 2 and np.std(dw) > 0 else 0.0
    return {"n": n, "word1_duplicates": dups,
            "word1_distance_vs_bitdistance_corr": corr,
            "note": "A nonzero correlation or any duplicate word1 would be a keystream-reuse lead."}


def synthetic_set(n: int, length: int, seed: int, reuse: bool) -> list[bytes]:
    """Controls: structured plaintexts XORed with a stream keystream.

    ``reuse=True`` uses one fixed keystream for all (reuse detectable); ``reuse=False`` uses a
    fresh keystream per item (undetectable). Plaintexts are near-identical (a fixed base plus
    light noise), mimicking repeats of one target.
    """
    rng = np.random.default_rng(seed)
    base = rng.integers(0, 256, length, dtype=np.uint8)

    def keystream(tag: bytes) -> np.ndarray:
        out = bytearray()
        c = 0
        while len(out) < length:
            out += hashlib.sha256(tag + c.to_bytes(4, "little")).digest()
            c += 1
        return np.frombuffer(bytes(out[:length]), np.uint8)

    fixed = keystream(b"fixed")
    items = []
    for i in range(n):
        plain = base.copy()
        flip = rng.choice(length, size=max(1, length // 200), replace=False)
        plain[flip] ^= rng.integers(1, 256, len(flip), dtype=np.uint8)
        ks = fixed if reuse else keystream(i.to_bytes(4, "little"))
        items.append((np.bitwise_xor(plain, ks)).tobytes())
    return items
