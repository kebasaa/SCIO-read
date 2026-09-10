"""Cross-scan oracle for candidate transforms that need not be spectrally smooth."""

from __future__ import annotations

import itertools
from concurrent.futures import ThreadPoolExecutor

import numpy as np

from . import decode, keyrecover


def _corr(a, b) -> float:
    a, b = np.asarray(a, float), np.asarray(b, float)
    if a.shape != b.shape or a.size < 16 or np.std(a) == 0 or np.std(b) == 0:
        return float("nan")
    return float(np.corrcoef(a, b)[0, 1])


def plaintext_repeatability(a: bytes, b: bytes) -> dict:
    """Best positive correlation across plausible integer representations."""
    best = {"score": -1.0, "view": None, "offset": None}
    for offset in (0, 4, 8, 12, 16):
        for view in decode.VIEWS:
            try:
                va = decode.to_intensity(a[offset:], view)
                vb = decode.to_intensity(b[offset:], view)
                score = _corr(va, vb)
            except Exception:
                continue
            if np.isfinite(score) and score > best["score"]:
                best = {"score": score, "view": view, "offset": offset}
    return best


def _mode_schemes():
    yield "ECB", "zero"
    # CBC IV affects only the first plaintext block; one scheme is enough for
    # the repeatability screen. Exact IV selection follows only after a hit.
    yield "CBC", "zero"
    for mode in ("CTR", "CFB", "OFB"):
        for scheme in decode.IV_SCHEMES:
            yield mode, scheme


def verify_repeatability(blobs: list[bytes], key: bytes, expansion_threshold: float = 0.12) -> dict:
    split = [decode.split_blob(blob) for blob in blobs]
    best = None
    for mode, scheme in _mode_schemes():
        plains = []
        try:
            for item in split[:2]:
                plains.append(decode.decrypt(item.body, key, mode=mode, iv=scheme, header=item.header))
        except Exception:
            continue
        initial = plaintext_repeatability(plains[0], plains[1])
        median = initial["score"]
        if median >= expansion_threshold and len(split) > 2:
            try:
                for item in split[2:]:
                    plains.append(decode.decrypt(item.body, key, mode=mode, iv=scheme, header=item.header))
                values = []
                for a, b in itertools.combinations(plains, 2):
                    values.append(plaintext_repeatability(a, b)["score"])
                median = float(np.median(values))
            except Exception:
                median = -1.0
        candidate = {"repeatability": median, "initial_pair": initial["score"],
                     "view": initial["view"], "offset": initial["offset"],
                     "mode": mode, "iv": scheme}
        if best is None or candidate["repeatability"] > best["repeatability"]:
            best = candidate
    return best


def search_identifier_keys(records, scope: str = "single", max_scans: int = 6,
                           workers: int = 8, hit_threshold: float = 0.5,
                           extra_device: dict | None = None) -> dict:
    """Search AES/key hypotheses using unchanged-target repeatability.

    ``scope='single'`` tests individual identifiers/versions; ``all`` includes
    pairwise constructions. The result is a hypothesis report, not a key claim.
    """
    blobs = [record.blobs["sample"] for record in records if "sample" in record.blobs][:max_scans]
    device = {}
    for record in records:
        for name, value in record.device.items():
            if value not in (None, ""):
                device.setdefault(name, value)
    if extra_device:
        device.update({name: value for name, value in extra_device.items() if value})
    candidates = keyrecover.candidate_keys_from_device(device)
    if scope == "single":
        candidates = {name: key for name, key in candidates.items() if "+" not in name}
    elif scope == "serial-pairs":
        candidates = {name: key for name, key in candidates.items()
                      if "case_serial+" in name or "+case_serial." in name or
                         "serial_fragment+" in name or "+serial_fragment." in name}
    elif scope != "all":
        raise ValueError("scope must be single, serial-pairs or all")
    by_key = {}
    for label, key in candidates.items():
        by_key.setdefault(key, []).append(label)
    items = [(" | ".join(labels), key) for key, labels in by_key.items()]

    def evaluate(item):
        label, key = item
        return {"label": label, **verify_repeatability(blobs, key)}

    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        rows = list(pool.map(evaluate, items))
    rows.sort(key=lambda row: row["repeatability"], reverse=True)
    hits = [row for row in rows if row["repeatability"] >= hit_threshold]
    return {"schema": "scio-key-repeatability/1", "scope": scope, "scans": len(blobs),
            "unique_keys": len(items), "hit_threshold": hit_threshold,
            "hits": hits, "best": rows[0] if rows else None, "top_candidates": rows[:50],
            "conclusion": "provisional repeatability hit" if hits else
                          "no enumerated AES identifier key produced repeatable plaintext"}
