"""Hypothesis-neutral diagnostics for opaque SCIO scan payloads."""

from __future__ import annotations

import bz2
import json
import lzma
import math
import struct
import zlib
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np

from . import decode


@dataclass
class BlobEvidence:
    size: int
    type_word: int
    second_word: int
    body_size: int
    body_entropy: float
    body_multiple_16: bool
    repeated_16b_blocks: int
    bit_one_fraction: float
    bit_plane_one_fraction: list[float]
    lag1_byte_autocorrelation: float
    compression_hits: list[str]
    best_numeric_view: str | None
    best_numeric_score: float
    top_layout_candidates: list[dict]


def _compression_hits(data: bytes) -> list[str]:
    hits = []
    for name, fn in (("zlib", zlib.decompress), ("bz2", bz2.decompress), ("lzma", lzma.decompress)):
        try:
            out = fn(data)
            if out:
                hits.append(name)
        except Exception:
            pass
    return hits


def _unpack12(data: bytes, order: str) -> np.ndarray:
    raw = np.frombuffer(data[:len(data) - len(data) % 3], dtype=np.uint8).reshape(-1, 3).astype(np.uint16)
    if order == "le":
        return np.column_stack((raw[:, 0] | ((raw[:, 1] & 0x0F) << 8),
                                (raw[:, 1] >> 4) | (raw[:, 2] << 4))).ravel().astype(float)
    return np.column_stack(((raw[:, 0] << 4) | (raw[:, 1] >> 4),
                            ((raw[:, 1] & 0x0F) << 8) | raw[:, 2])).ravel().astype(float)


def screen_layouts(blob: bytes, offsets=range(0, 16)) -> list[dict]:
    """Rank common endian/alignment/12-bit layouts without calling any a decode."""
    rows = []
    for offset in offsets:
        data = blob[offset:]
        for view in decode.VIEWS:
            vector = decode.to_intensity(data, view)
            rows.append({"offset": offset, "view": view,
                         "smoothness": decode.smoothness(vector),
                         "lag1": decode.autocorr1(vector)})
        for order in ("le", "be"):
            vector = _unpack12(data, order)
            rows.append({"offset": offset, "view": f"u12{order}",
                         "smoothness": decode.smoothness(vector),
                         "lag1": decode.autocorr1(vector)})
    for row in rows:
        row["score"] = 0.6 * row["smoothness"] + 0.4 * max(0.0, row["lag1"])
    return sorted(rows, key=lambda row: row["score"], reverse=True)


def analyze_blob(blob: bytes, body_offset: int = 8) -> BlobEvidence:
    if len(blob) < 8:
        raise ValueError("blob shorter than observed eight-byte prefix")
    type_word, second_word = struct.unpack_from("<II", blob, 0)
    body = blob[body_offset:]
    blocks = [body[i:i + 16] for i in range(0, len(body) - 15, 16)]
    repeated = len(blocks) - len(set(blocks))
    one_bits = sum(int(b).bit_count() for b in body)
    bit_planes = [sum((b >> bit) & 1 for b in body) / len(body) if body else math.nan
                  for bit in range(8)]
    byte_values = np.frombuffer(body, dtype=np.uint8).astype(float)
    lag1 = decode.autocorr1(byte_values)
    numeric = decode.plaintext_score(body)
    layouts = screen_layouts(blob)[:5]
    return BlobEvidence(
        size=len(blob), type_word=type_word, second_word=second_word,
        body_size=len(body), body_entropy=round(decode.entropy(body), 6),
        body_multiple_16=(len(body) % 16 == 0), repeated_16b_blocks=repeated,
        bit_one_fraction=(one_bits / (len(body) * 8)) if body else math.nan,
        bit_plane_one_fraction=bit_planes, lag1_byte_autocorrelation=lag1,
        compression_hits=_compression_hits(body), best_numeric_view=numeric["view"],
        best_numeric_score=round(float(numeric["score"]), 6),
        top_layout_candidates=layouts,
    )


def hamming_fraction(a: bytes, b: bytes) -> float:
    """Bit Hamming distance over the common length."""
    n = min(len(a), len(b))
    if n == 0:
        return math.nan
    changed = sum((x ^ y).bit_count() for x, y in zip(a[:n], b[:n]))
    return changed / (n * 8)


def corpus_report(records) -> dict:
    blob_rows = []
    by_kind: dict[str, list[tuple[str, bytes]]] = {}
    for record in records:
        for kind, blob in record.blobs.items():
            ev = analyze_blob(blob)
            blob_rows.append({"record_id": record.record_id, "label": record.label,
                              "kind": kind, **asdict(ev)})
            by_kind.setdefault(kind, []).append((record.record_id, blob))
    adjacent = []
    for kind, values in by_kind.items():
        for (id_a, a), (id_b, b) in zip(values, values[1:]):
            adjacent.append({"kind": kind, "record_a": id_a, "record_b": id_b,
                             "whole_hamming": hamming_fraction(a, b),
                             "body_hamming": hamming_fraction(a[8:], b[8:])})
    entropies = [r["body_entropy"] for r in blob_rows]
    return {
        "schema": "scio-transform-evidence/1",
        "interpretation": {
            "status": "unresolved",
            "compatible_hypotheses": ["packed/structured", "compressed", "obfuscated", "encrypted"],
            "warning": "Entropy, block alignment and smoothness are screening evidence, not proof.",
        },
        "summary": {"records": len(records), "blobs": len(blob_rows),
                    "entropy_min": min(entropies) if entropies else None,
                    "entropy_median": float(np.median(entropies)) if entropies else None,
                    "entropy_max": max(entropies) if entropies else None},
        "blobs": blob_rows,
        "adjacent_pairs": adjacent,
    }


def write_report(report: dict, path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, allow_nan=False), encoding="utf-8")
    return path
