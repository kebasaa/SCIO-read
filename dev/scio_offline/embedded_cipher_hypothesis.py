"""Bounded TEA/XTEA tests for opaque SCIO scan bodies.

These embedded ciphers are hypotheses only. Search success requires repeated
captures of an unchanged target to decrypt into mutually correlated buffers.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import numpy as np

from . import decode, keyrecover
from .repeatability import plaintext_repeatability

MASK = np.uint64(0xFFFFFFFF)
DELTA = 0x9E3779B9


def _words(data, endian):
    usable = len(data) - len(data) % 8
    return np.frombuffer(data[:usable], dtype=">u4" if endian == "big" else "<u4").astype(np.uint64).reshape(-1, 2)


def _pack(words, endian):
    return (words & MASK).astype(">u4" if endian == "big" else "<u4").tobytes()


def _key_words(key, endian):
    if len(key) != 16:
        raise ValueError("TEA/XTEA key must be 16 bytes")
    return np.frombuffer(key, dtype=">u4" if endian == "big" else "<u4").astype(np.uint64)


def tea_ecb(data, key, endian="big", decrypt=True):
    w, k = _words(data, endian), _key_words(key, endian)
    v0, v1 = w[:, 0].copy(), w[:, 1].copy()
    with np.errstate(over="ignore"):
        total = (DELTA * 32) & 0xFFFFFFFF if decrypt else 0
        for _ in range(32):
            if decrypt:
                v1 = (v1 - ((((v0 << 4) + k[2]) ^ (v0 + total) ^ ((v0 >> 5) + k[3])) & MASK)) & MASK
                v0 = (v0 - ((((v1 << 4) + k[0]) ^ (v1 + total) ^ ((v1 >> 5) + k[1])) & MASK)) & MASK
                total = (total - DELTA) & 0xFFFFFFFF
            else:
                total = (total + DELTA) & 0xFFFFFFFF
                v0 = (v0 + ((((v1 << 4) + k[0]) ^ (v1 + total) ^ ((v1 >> 5) + k[1])) & MASK)) & MASK
                v1 = (v1 + ((((v0 << 4) + k[2]) ^ (v0 + total) ^ ((v0 >> 5) + k[3])) & MASK)) & MASK
    return _pack(np.column_stack((v0, v1)), endian)


def xtea_ecb(data, key, endian="big", decrypt=True):
    w, k = _words(data, endian), _key_words(key, endian)
    v0, v1 = w[:, 0].copy(), w[:, 1].copy()
    with np.errstate(over="ignore"):
        total = (DELTA * 32) & 0xFFFFFFFF if decrypt else 0
        for _ in range(32):
            if decrypt:
                v1 = (v1 - (((((v0 << 4) ^ (v0 >> 5)) + v0) ^ (total + k[(total >> 11) & 3])) & MASK)) & MASK
                total = (total - DELTA) & 0xFFFFFFFF
                v0 = (v0 - (((((v1 << 4) ^ (v1 >> 5)) + v1) ^ (total + k[total & 3])) & MASK)) & MASK
            else:
                v0 = (v0 + (((((v1 << 4) ^ (v1 >> 5)) + v1) ^ (total + k[total & 3])) & MASK)) & MASK
                total = (total + DELTA) & 0xFFFFFFFF
                v1 = (v1 + (((((v0 << 4) ^ (v0 >> 5)) + v0) ^ (total + k[(total >> 11) & 3])) & MASK)) & MASK
    return _pack(np.column_stack((v0, v1)), endian)


def decrypt_body(body, key, cipher, endian, mode):
    plain = (tea_ecb if cipher == "TEA" else xtea_ecb)(body, key, endian, True)
    if mode == "ECB":
        return plain
    c = np.frombuffer(body[:len(plain)], dtype=np.uint8).reshape(-1, 8)
    p = np.frombuffer(plain, dtype=np.uint8).reshape(-1, 8).copy()
    p[1:] ^= c[:-1]  # zero-IV CBC; the first block cannot affect our conclusion
    return p.tobytes()


def search_embedded_ciphers(records, max_scans=6, workers=8, extra_device=None, hit_threshold=0.5):
    blobs = [decode.split_blob(r.blobs["sample"]).body for r in records if "sample" in r.blobs][:max_scans]
    device = {}
    for record in records:
        device.update({k: v for k, v in record.device.items() if v not in (None, "")})
    if extra_device:
        device.update({k: v for k, v in extra_device.items() if v})
    by_key = {}
    for label, key in keyrecover.candidate_keys_from_device(device).items():
        if len(key) == 16 and "+" not in label:
            by_key.setdefault(key, []).append(label)

    def evaluate(item):
        key, labels = item
        best = None
        for cipher in ("TEA", "XTEA"):
            for endian in ("big", "little"):
                for mode in ("ECB", "CBC-zero"):
                    plains = [decrypt_body(blob, key, cipher, endian, mode) for blob in blobs]
                    first = plaintext_repeatability(plains[0], plains[1])
                    scores = [first["score"]]
                    if first["score"] >= 0.12:
                        scores = [plaintext_repeatability(plains[0], p)["score"] for p in plains[1:]]
                    row = {"label": " | ".join(labels), "cipher": cipher, "endian": endian,
                           "mode": mode, "repeatability": float(np.median(scores)),
                           "initial_pair": first["score"], "view": first["view"], "offset": first["offset"]}
                    if best is None or row["repeatability"] > best["repeatability"]:
                        best = row
        return best

    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        rows = list(pool.map(evaluate, by_key.items()))
    rows.sort(key=lambda r: r["repeatability"], reverse=True)
    hits = [r for r in rows if r["repeatability"] >= hit_threshold]
    return {"schema": "scio-embedded-cipher-hypothesis/1", "scans": len(blobs),
            "unique_keys": len(by_key), "transforms_per_key": 8, "hit_threshold": hit_threshold,
            "hits": hits, "best": rows[0] if rows else None, "top_candidates": rows[:50],
            "conclusion": "provisional repeatability hit" if hits else
            "no enumerated TEA/XTEA identifier key produced repeatable plaintext"}
