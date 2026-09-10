"""Test lightweight nonce/seed stream transforms before assuming strong crypto."""

from __future__ import annotations

import hashlib
import itertools
import struct
import zlib

import numpy as np

from . import decode
from .evidence import _compression_hits


def _word_stream(seed: int, size: int, kind: str, byteorder: str) -> bytes:
    state = seed & 0xFFFFFFFF
    words = []
    count = (size + 3) // 4
    if kind == "mt19937":
        rng = np.random.Generator(np.random.MT19937(state))
        raw = rng.integers(0, 2**32, count, dtype=np.uint32)
        return raw.astype("<u4" if byteorder == "little" else ">u4").tobytes()[:size]
    constants = {
        "lcg_nr": (1664525, 1013904223),
        "lcg_glibc": (1103515245, 12345),
        "lcg_msvc": (214013, 2531011),
    }
    for _ in range(count):
        if kind in constants:
            a, c = constants[kind]
            state = (a * state + c) & 0xFFFFFFFF
        elif kind == "xorshift32":
            state ^= (state << 13) & 0xFFFFFFFF
            state ^= state >> 17
            state ^= (state << 5) & 0xFFFFFFFF
            state &= 0xFFFFFFFF
        else:
            raise ValueError(kind)
        words.append(state.to_bytes(4, byteorder))
    return b"".join(words)[:size]


def _hash_counter(seed: int, size: int, byteorder: str) -> bytes:
    seed_bytes = seed.to_bytes(4, byteorder)
    chunks = []
    for counter in range((size + 31) // 32):
        chunks.append(hashlib.sha256(seed_bytes + counter.to_bytes(4, byteorder)).digest())
    return b"".join(chunks)[:size]


def keystream(seed: int, size: int, kind: str, byteorder: str = "little") -> bytes:
    if kind == "sha256_counter":
        return _hash_counter(seed, size, byteorder)
    return _word_stream(seed, size, kind, byteorder)


def _identifier_words(device: dict) -> dict[str, int]:
    out = {"none": 0}
    fields = ("device_id", "aptina_field", "aptinaId", "dsp_id", "deviceDspId",
              "ble_id", "deviceBleId", "serial_number", "device_serial_fragment",
              "i2s_tag_config")
    for field in fields:
        value = device.get(field)
        if value in (None, ""):
            continue
        text = str(value).strip()
        compact = text.replace(":", "").replace("-", "").replace(" ", "")
        try:
            raw = bytes.fromhex(compact)
        except ValueError:
            raw = text.encode()
        out[f"{field}.crc32"] = zlib.crc32(raw) & 0xFFFFFFFF
        for i in range(0, len(raw) - 3, 4):
            out[f"{field}.word{i // 4}le"] = int.from_bytes(raw[i:i + 4], "little")
            out[f"{field}.word{i // 4}be"] = int.from_bytes(raw[i:i + 4], "big")
    return out


def _xor(a: bytes, b: bytes) -> bytes:
    return bytes(x ^ y for x, y in zip(a, b))


def _corr(a, b) -> float:
    a, b = np.asarray(a, float), np.asarray(b, float)
    if a.shape != b.shape or a.size < 8 or np.std(a) == 0 or np.std(b) == 0:
        return float("nan")
    return float(np.corrcoef(a, b)[0, 1])


def stream_hypothesis_report(records, blob_kind: str = "sample") -> dict:
    blobs = []
    common_modifier_names = None
    modifier_maps = []
    for record in records:
        blob = record.blobs.get(blob_kind)
        if not blob or len(blob) < 8:
            continue
        modifiers = _identifier_words(record.device)
        modifier_maps.append(modifiers)
        common_modifier_names = set(modifiers) if common_modifier_names is None else common_modifier_names & set(modifiers)
        blobs.append((record, blob[8:], struct.unpack_from("<I", blob, 4)[0]))
    if not blobs:
        return {"schema": "scio-stream-hypothesis/1", "candidates": [], "supported": False}

    kinds = ("lcg_nr", "lcg_glibc", "lcg_msvc", "xorshift32", "mt19937", "sha256_counter")
    rows = []
    for kind, byteorder, modifier_name, operation in itertools.product(
            kinds, ("little", "big"), sorted(common_modifier_names or {"none"}), ("xor", "add")):
        decoded = []
        screens = []
        compression_hits = 0
        for index, (_, body, header_word) in enumerate(blobs):
            modifier = modifier_maps[index][modifier_name]
            seed = ((header_word ^ modifier) if operation == "xor" else (header_word + modifier)) & 0xFFFFFFFF
            plain = _xor(body, keystream(seed, len(body), kind, byteorder))
            score = decode.plaintext_score(plain)
            screens.append(score["score"])
            compression_hits += bool(_compression_hits(plain))
            decoded.append(decode.to_intensity(plain, score["view"] or "u8"))
        correlations = [_corr(a, b) for a, b in itertools.combinations(decoded[:12], 2)]
        correlations = [x for x in correlations if np.isfinite(x)]
        row = {"generator": kind, "byteorder": byteorder, "modifier": modifier_name,
               "operation": operation, "median_plaintext_score": float(np.median(screens)),
               "maximum_plaintext_score": float(np.max(screens)),
               "median_repeat_correlation": float(np.median(correlations)) if correlations else None,
               "compression_hits": compression_hits}
        row["combined_score"] = row["median_plaintext_score"] + max(0, row["median_repeat_correlation"] or 0)
        rows.append(row)
    rows.sort(key=lambda row: row["combined_score"], reverse=True)
    best = rows[0] if rows else None
    supported = bool(best and (best["compression_hits"] or
                     (best["median_plaintext_score"] >= 0.5 and
                      (best["median_repeat_correlation"] or 0) >= 0.5)))
    return {"schema": "scio-stream-hypothesis/1", "records": len(blobs),
            "candidate_count": len(rows), "supported": supported,
            "best": best, "top_candidates": rows[:50],
            "warning": "Negative results cover only enumerated seed/PRNG constructions."}
