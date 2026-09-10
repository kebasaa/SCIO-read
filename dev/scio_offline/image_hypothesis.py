"""Tests for a direct image or image-projection interpretation of scan blobs.

The optical instrument uses an imager internally, so this is physically
motivated. The tests below require spatial structure and cross-scan
repeatability; merely reshaping bytes into a rectangle is not evidence.
"""

from __future__ import annotations

import itertools
import math

import numpy as np

from .evidence import _unpack12


IMAGE_SIGNATURES = {
    "png": b"\x89PNG\r\n\x1a\n", "jpeg": b"\xff\xd8\xff", "bmp": b"BM",
    "tiff_le": b"II*\x00", "tiff_be": b"MM\x00*", "gif": b"GIF8",
}


def file_signature(blob: bytes) -> str | None:
    return next((name for name, magic in IMAGE_SIGNATURES.items() if blob.startswith(magic)), None)


def image_vectors(blob: bytes, offset: int = 8) -> dict[str, np.ndarray]:
    data = blob[offset:]
    usable2 = len(data) - len(data) % 2
    return {
        "u8": np.frombuffer(data, dtype=np.uint8).astype(float),
        "u16le": np.frombuffer(data[:usable2], dtype="<u2").astype(float),
        "u16be": np.frombuffer(data[:usable2], dtype=">u2").astype(float),
        "u12le": _unpack12(data, "le"),
        "u12be": _unpack12(data, "be"),
    }


def factor_shapes(n: int, minimum: int = 8, maximum: int = 128) -> list[tuple[int, int]]:
    shapes = []
    for rows in range(minimum, min(maximum, int(math.sqrt(n))) + 1):
        if n % rows == 0 and minimum <= n // rows <= maximum:
            shapes.extend([(rows, n // rows), (n // rows, rows)])
    return sorted(set(shapes))


def _corr(a, b) -> float:
    a, b = np.asarray(a, float).ravel(), np.asarray(b, float).ravel()
    if a.size != b.size or a.size < 8 or np.std(a) == 0 or np.std(b) == 0:
        return float("nan")
    return float(np.corrcoef(a, b)[0, 1])


def spatial_metrics(vector: np.ndarray, shape: tuple[int, int], order: str = "C") -> dict:
    img = np.asarray(vector, float).reshape(shape, order=order)
    horizontal = _corr(img[:, :-1], img[:, 1:])
    vertical = _corr(img[:-1, :], img[1:, :])
    yy, xx = np.indices(shape)
    radius = np.hypot(yy - (shape[0] - 1) / 2, xx - (shape[1] - 1) / 2)
    bins = np.minimum((radius / (radius.max() or 1) * 15).astype(int), 15)
    means = np.array([img[bins == i].mean() if np.any(bins == i) else img.mean() for i in range(16)])
    fitted = means[bins]
    total = np.sum((img - img.mean()) ** 2)
    radial_r2 = 1.0 - np.sum((img - fitted) ** 2) / total if total else 0.0
    return {"shape": list(shape), "order": order, "horizontal_corr": horizontal,
            "vertical_corr": vertical, "radial_variance_explained": float(radial_r2),
            "spatial_score": float(max(0, horizontal, vertical, radial_r2))}


def image_hypothesis_report(records, blob_kind: str = "sample") -> dict:
    prepared = []
    signatures = []
    for record in records:
        blob = record.blobs.get(blob_kind)
        if not blob:
            continue
        sig = file_signature(blob)
        if sig:
            signatures.append({"record_id": record.record_id, "format": sig})
        prepared.append((record, image_vectors(blob)))

    spatial = []
    for record, views in prepared:
        for view, vector in views.items():
            for shape in factor_shapes(len(vector)):
                for order in ("C", "F"):
                    spatial.append({"record_id": record.record_id, "label": record.label,
                                    "view": view, **spatial_metrics(vector, shape, order)})
    spatial.sort(key=lambda row: row["spatial_score"], reverse=True)

    within, between = [], []
    for (rec_a, views_a), (rec_b, views_b) in itertools.combinations(prepared, 2):
        target = within if rec_a.label == rec_b.label else between
        for view in sorted(set(views_a) & set(views_b)):
            corr = _corr(views_a[view], views_b[view])
            if np.isfinite(corr):
                target.append({"view": view, "label_a": rec_a.label, "label_b": rec_b.label,
                               "record_a": rec_a.record_id, "record_b": rec_b.record_id,
                               "pixel_correlation": corr})
    within_values = [x["pixel_correlation"] for x in within]
    between_values = [x["pixel_correlation"] for x in between]
    within_median = float(np.median(within_values)) if within_values else None
    between_median = float(np.median(between_values)) if between_values else None
    best_spatial = spatial[0]["spatial_score"] if spatial else None
    supported = bool(within_median is not None and between_median is not None and
                     within_median >= 0.5 and within_median - between_median >= 0.2 and
                     best_spatial is not None and best_spatial >= 0.2)
    return {
        "schema": "scio-image-hypothesis/1", "blob_kind": blob_kind,
        "file_signatures": signatures,
        "summary": {"records": len(prepared), "within_label_pairs": len(within),
                    "between_label_pairs": len(between), "within_pixel_corr_median": within_median,
                    "between_pixel_corr_median": between_median, "best_spatial_score": best_spatial,
                    "direct_image_supported": supported},
        "top_spatial_candidates": spatial[:50],
        "within_label_repeatability": within[:200],
        "warning": "Failure rejects direct tested layouts, not an image hidden behind another transform.",
    }
