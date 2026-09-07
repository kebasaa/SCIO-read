"""Candidate transforms for SCIO payload research.

AES is one hypothesis among packing, compression and obfuscation. Block
alignment and high entropy are not proof of encryption, and the second header
word is not proven to be a nonce. Functions here evaluate explicitly supplied
candidates; a smoothness score alone never establishes a successful decode.
"""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass

import numpy as np
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from .protocol import BLOB_TYPE_GRADIENT, BLOB_TYPE_SAMPLE, parse_blob_header

MODES = ("ECB", "CBC", "CTR", "CFB", "OFB")
IV_SCHEMES = ("zero", "header8_zero8", "zero8_header8", "header8_x2", "first_block")
# Views scored by the oracle.  The on-device binned data is integer counts, so
# float32 is deliberately excluded: random bytes read as float32 contain a few
# astronomically large values that make any curve look "smooth".
VIEWS = ("u8", "u16le", "u16be", "u32le", "u32be")
ALL_VIEWS = VIEWS + ("f32le",)


@dataclass
class Blob:
    type: int
    nonce: int
    header: bytes
    body: bytes

    @property
    def kind(self) -> str:
        if self.type == BLOB_TYPE_GRADIENT:
            return "gradient"
        if self.type == BLOB_TYPE_SAMPLE:
            return "sample_or_dark"
        return "unknown(0x%X)" % self.type


def split_blob(blob: bytes) -> Blob:
    """Split the observed 8-byte prefix from the opaque body.

    ``Blob.nonce`` is a legacy field name for the unclassified second word.
    """
    h = parse_blob_header(blob)
    return Blob(h["type"], h["nonce"], bytes(blob[:8]), bytes(h["body"]))


def make_iv(scheme: str, header: bytes, body: bytes) -> bytes:
    """Build a 16-byte IV / initial counter block for a named scheme."""
    if scheme == "zero":
        return bytes(16)
    if scheme == "header8_zero8":
        return header[:8] + bytes(8)
    if scheme == "zero8_header8":
        return bytes(8) + header[:8]
    if scheme == "header8_x2":
        return header[:8] + header[:8]
    if scheme == "first_block":
        return body[:16]
    raise ValueError("unknown IV scheme: %s" % scheme)


def decrypt(body: bytes, key: bytes, mode: str = "CBC", iv=None, header: bytes = b"") -> bytes:
    """AES-decrypt ``body`` (multiple of 16 B) with ``key`` (16/24/32 B).

    ``iv`` is a 16-byte value or a scheme name from :data:`IV_SCHEMES`.  With
    ``first_block`` the first block is treated as the IV and dropped.
    """
    if len(key) not in (16, 24, 32):
        raise ValueError("AES key must be 16, 24 or 32 bytes")
    body = bytes(body)
    body = body[: len(body) - len(body) % 16]
    if isinstance(iv, str):
        scheme = iv
        iv = make_iv(scheme, header, body)
        if scheme == "first_block":
            body = body[16:]
    if iv is None:
        iv = bytes(16)
    m = {
        "ECB": lambda: modes.ECB(),
        "CBC": lambda: modes.CBC(iv),
        "CTR": lambda: modes.CTR(iv),
        "CFB": lambda: modes.CFB(iv),
        "OFB": lambda: modes.OFB(iv),
    }[mode]()
    d = Cipher(algorithms.AES(key), m, backend=default_backend()).decryptor()
    return d.update(body) + d.finalize()


def entropy(data: bytes) -> float:
    """Shannon entropy in bits per byte (8.0 == uniformly random)."""
    if not data:
        return 0.0
    n = len(data)
    return -sum(c / n * math.log2(c / n) for c in Counter(data).values())


def to_intensity(plain: bytes, view: str = "u16le") -> np.ndarray:
    """Interpret plaintext bytes as a numeric vector."""
    dt = {"u8": "u1", "u16le": "<u2", "u16be": ">u2", "u32le": "<u4",
          "u32be": ">u4", "f32le": "<f4"}[view]
    size = np.dtype(dt).itemsize
    usable = len(plain) - len(plain) % size
    with np.errstate(all="ignore"):
        v = np.frombuffer(plain[:usable], dtype=dt).astype(float)
    return v


def smoothness(v: np.ndarray) -> float:
    """Fraction of consecutive deltas that are small relative to the range.

    A binned NIR intensity curve is smooth: most |x[i+1]-x[i]| are a small
    fraction of max-min.  Random data scores ~0.05, a real curve close to 1.
    """
    v = np.asarray(v, dtype=float)
    if v.size < 8 or not np.isfinite(v).all():
        return 0.0
    # Robust range (2nd-98th percentile) so a single outlier cannot inflate it.
    rng = np.percentile(v, 98) - np.percentile(v, 2)
    if rng <= 0:
        return 0.0
    d = np.abs(np.diff(v)) / rng
    return float(np.mean(d < 0.02))


def autocorr1(v: np.ndarray) -> float:
    """Lag-1 autocorrelation (random -> ~0, smooth curve -> ~1)."""
    v = np.asarray(v, dtype=float)
    if v.size < 8 or np.std(v) == 0:
        return 0.0
    a = v[:-1] - v.mean()
    b = v[1:] - v.mean()
    return float(np.sum(a * b) / np.sum((v - v.mean()) ** 2))


def plaintext_score(plain: bytes) -> dict:
    """Score how much ``plain`` looks like decrypted spectral data.

    This is a screening heuristic, not evidence of decryption. A candidate
    must also pass cross-scan, calibration and held-out spectral validation.
    """
    ent = entropy(plain)
    best = {"view": None, "smooth": 0.0, "acorr": 0.0}
    for view in VIEWS:
        try:
            v = to_intensity(plain, view)
        except Exception:
            continue
        if v.size < 64:
            continue
        # A float view of non-spectral bytes is mostly NaN/inf; reject it so it
        # cannot masquerade as "smooth" on the few finite values that survive.
        finite = np.isfinite(v)
        if finite.mean() < 0.98:
            continue
        v = v[finite]
        s, a = smoothness(v), max(0.0, autocorr1(v))
        if s + a > best["smooth"] + best["acorr"]:
            best = {"view": view, "smooth": s, "acorr": a}
    ent_term = max(0.0, (7.5 - ent) / 7.5)   # 0 at random-level entropy
    score = 0.5 * best["smooth"] + 0.3 * best["acorr"] + 0.2 * min(1.0, ent_term * 3)
    return {"score": float(score), "entropy": ent, **best}


def reflectance(sample, dark, gradient=None, white=None, white_dark=None, white_gradient=None):
    """Physical combination of decrypted intensity vectors.

    Conceptually R = (S - D) / (W - W_D).  The gradient blobs are what the
    server model used in addition; how it used them is unknown, so they are
    accepted but not applied here.  Refine against a fixture's ``spec_data``
    once decryption works.
    """
    s = np.asarray(sample, float) - np.asarray(dark, float)
    if white is None:
        return s
    w = np.asarray(white, float) - np.asarray(white_dark if white_dark is not None else 0, float)
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(w != 0, s / w, np.nan)


def normalize_curve(values: np.ndarray, method: str = "robust") -> np.ndarray:
    """Return a scale-free curve while preserving wavelength order."""
    v = np.asarray(values, dtype=float)
    if v.ndim != 1 or v.size == 0:
        raise ValueError("values must be a non-empty one-dimensional vector")
    if method == "robust":
        lo, hi = np.nanpercentile(v, [2, 98])
        if not np.isfinite(lo) or not np.isfinite(hi) or hi <= lo:
            raise ValueError("curve has no finite robust range")
        return np.clip((v - lo) / (hi - lo), 0.0, 1.0)
    if method == "l2":
        centered = v - np.nanmean(v)
        norm = np.linalg.norm(np.nan_to_num(centered))
        if norm == 0:
            raise ValueError("curve has zero norm")
        return centered / norm
    raise ValueError(f"unknown normalization method: {method}")


def wavelength_axis(start_nm: float = 740.0, stop_nm: float = 1070.0,
                    count: int = 331) -> np.ndarray:
    """Return the archived server axis, not an asserted native pixel axis."""
    if count < 2 or stop_nm <= start_nm:
        raise ValueError("invalid wavelength axis")
    return np.linspace(start_nm, stop_nm, count)
