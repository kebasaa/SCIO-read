"""Arithmetic constraints from file and blob sizes on layout hypotheses.

Sizes are the only facts we hold about the calibration tables and scan bodies.
This enumerates every split ``prefix + count * width`` (prefix 0/2/4/8 bytes,
width 1/2/4/8 bytes) and flags counts that a hypothesis would need: multiples of
12 (the teardown's 12 filtered receptors), 331 (output bands), or plain-pixel
counts. It produces constraints, never a layout: a size that *fits* proves nothing.
"""
from __future__ import annotations

SIZES = {
    "tables": {"deadPixelsIndices": 1714, "centers": 96, "bins": 140, "nPixelsPerBin": 1166},
    "bodies": {"sample_or_dark": 1792, "gradient_e": 1648, "gradient_o": 1408},
    "firmware": {"dsp_boot": 7284, "dsp_dec": 14600, "dsp_op": 32628, "ble_runtime": 119233},
}
PREFIXES = (0, 2, 4, 8)
WIDTHS = (1, 2, 4, 8)
RECEPTORS = 12
BANDS = 331


def factorise(n: int) -> dict[int, int]:
    out, p = {}, 2
    while p * p <= n:
        while n % p == 0:
            out[p] = out.get(p, 0) + 1
            n //= p
        p += 1
    if n > 1:
        out[n] = out.get(n, 0) + 1
    return out


def splits(size: int) -> list[dict]:
    rows = []
    for prefix in PREFIXES:
        for width in WIDTHS:
            rest = size - prefix
            if rest > 0 and rest % width == 0:
                count = rest // width
                rows.append({"prefix": prefix, "width": width, "count": count,
                             "per_receptor": count // RECEPTORS if count % RECEPTORS == 0 else None,
                             "multiple_of_bands": count % BANDS == 0})
    return rows


def packed_fits(size: int, bits=(10, 12, 14)) -> dict[int, bool]:
    return {b: (size * 8) % b == 0 for b in bits}


def report() -> dict:
    out = {}
    for group, sizes in SIZES.items():
        out[group] = {name: {"bytes": n, "factors": {str(k): v for k, v in factorise(n).items()},
                             "multiple_of_16": n % 16 == 0, "splits": splits(n),
                             "packed_bits_fit": {str(k): v for k, v in packed_fits(n).items()}}
                      for name, n in sizes.items()}
    e, o = SIZES["bodies"]["gradient_e"], SIZES["bodies"]["gradient_o"]
    out["cross_generation"] = {"gradient_difference_bytes": e - o,
                               "difference_aes_blocks": (e - o) / 16,
                               "difference_per_receptor": (e - o) / RECEPTORS,
                               "sample_size_unchanged": True}
    return out
