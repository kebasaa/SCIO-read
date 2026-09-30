"""Simulated decoding servers, to validate the malleability classifier.

A classifier that has only ever seen the real server cannot be validated: we do not
know the right answer there. So this module builds servers whose transform we *do*
know, runs the identical probe protocol against them, and requires the classifier to
return the right label - or ``"undetermined"``, never a wrong one.

The simulator is deliberately **not benign**. A dense random binning matrix would make
every flip move every band and make the classifier look worse than it is; a perfect
window onto the plaintext would make it look better. Real behaviour sits between, so
the server here has:

* banded, overlapping binning (~2.7 pixels per band), with a wider kernel as a variant
  standing in for interpolation;
* an optional scrambled pixel order, so neighbouring bytes do not feed neighbouring bands;
* masked top bits, dead pixels, an ``InvalidScan`` range check that rejects garbled
  input, and a global-normalisation variant that breaks locality on purpose;
* nine transforms: AES-CTR / OFB / CFB / CBC / ECB, a seed-only XOR PRNG stream, a
  block DCT, delta coding, an adaptive Rice decoder (variable length, so damage
  desynchronises downstream) and a whole-body-authenticated mode.

The plaintext model (896 x u16) is the hypothesis from sizes in ``dev/README.md``. The
simulator needs *a* model to exercise the classifier; it is not evidence about the
real one.
"""

from __future__ import annotations

import struct

import numpy as np
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from scio import store

from .malleability import BODY, HEADER, N_BANDS, N_PX, OracleError, get_blob

MODES = ("ctr", "ofb", "cfb", "cbc", "ecb", "xor_prng", "dct", "delta", "adaptive", "auth")

#: what the classifier should say for each mode
TRUTH = {"ctr": "stream", "ofb": "stream", "xor_prng": "stream",
         "cbc": "chained_block", "cfb": "chained_block", "ecb": "ecb_like",
         "dct": "block_transform", "delta": "delta_coding",
         "adaptive": "adaptive_stream", "auth": "undetermined"}

_ROLES = ("sample", "sample_dark", "sample_white", "sample_white_dark")


def binning_matrix(kind: str = "box") -> np.ndarray:
    """N_BANDS x N_PX non-negative, banded, row-normalised."""
    centers = np.linspace(0, N_PX - 1, N_BANDS)
    half = 2.7 if kind == "box" else 5.4            # the wider kernel stands in for interpolation
    x = np.arange(N_PX)[None, :]
    w = np.clip(1.0 - np.abs(x - centers[:, None]) / half, 0.0, None)
    return w / w.sum(axis=1, keepdims=True)


def _dct8() -> np.ndarray:
    n = np.arange(8)
    c = np.sqrt(2.0 / 8) * np.cos((2 * n[None, :] + 1) * n[:, None] * np.pi / 16)
    c[0] /= np.sqrt(2)
    return c


_C8 = _dct8()


# ---------------------------------------------------------------- adaptive Rice coder
def _rice_k(history: list) -> int:
    mean = sum(history[-8:]) / max(1, len(history[-8:]))
    return max(0, int(np.log2(mean + 1)) - 1) if history else 7


def _rice_encode(values: np.ndarray, rng) -> bytes:
    bits, hist = [], []
    for v in values.tolist():
        k = _rice_k(hist)
        q = v >> k
        bits += [1] * q + [0] + [(v >> i) & 1 for i in range(k - 1, -1, -1)]
        hist.append(v)
    bits = bits[: BODY * 8]
    pad = BODY * 8 - len(bits)
    bits += rng.integers(0, 2, pad).tolist()       # the unused tail is random padding
    return np.packbits(np.array(bits, dtype=np.uint8)).tobytes()


def _rice_decode(body: bytes) -> np.ndarray:
    bits = np.unpackbits(np.frombuffer(body, dtype=np.uint8)).tolist()
    pos, out, hist = 0, [], []
    for _ in range(N_PX):
        k = _rice_k(hist)
        q = 0
        while pos < len(bits) and bits[pos] == 1 and q < 64:
            q += 1
            pos += 1
        pos += 1                                   # the terminating zero
        r = 0
        for _i in range(k):
            r = (r << 1) | (bits[pos] if pos < len(bits) else 0)
            pos += 1
        v = (q << k) | r
        out.append(v)
        hist.append(v)
    return np.array(out, dtype=float)


# --------------------------------------------------------------------- encode/decode
def _aes(mode: str, key: bytes, iv: bytes):
    m = {"ctr": modes.CTR(iv), "ofb": modes.OFB(iv), "cfb": modes.CFB(iv),
         "cbc": modes.CBC(iv), "ecb": modes.ECB()}[mode]
    return Cipher(algorithms.AES(key), m)


def _prng_stream(header8: bytes) -> np.ndarray:
    seed = struct.unpack("<I", header8[4:8])[0]
    return np.random.default_rng(seed).integers(0, 256, BODY, dtype=np.uint8)


def encode(mode: str, pix: np.ndarray, header8: bytes, key: bytes, rng) -> bytes:
    iv = header8 + bytes(8)
    plain = np.asarray(pix, dtype="<u2").tobytes()
    if mode in ("ctr", "ofb", "cfb", "cbc", "ecb", "auth"):
        m = "ctr" if mode == "auth" else mode
        return _aes(m, key, iv).encryptor().update(plain)
    if mode == "xor_prng":
        return bytes(np.frombuffer(plain, dtype=np.uint8) ^ _prng_stream(header8))
    if mode == "dct":
        coefs = (_C8 @ np.asarray(pix, float).reshape(-1, 8).T).T
        return np.round(coefs).astype("<i2").tobytes()
    if mode == "delta":
        p = np.asarray(pix, np.int64)
        return np.diff(p, prepend=0).astype("<i2").tobytes()
    if mode == "adaptive":
        return _rice_encode(np.asarray(pix, np.int64), rng)
    raise ValueError(mode)


def decode(mode: str, body: bytes, header8: bytes, key: bytes) -> np.ndarray:
    iv = header8 + bytes(8)
    if mode in ("ctr", "ofb", "cfb", "cbc", "ecb", "auth"):
        m = "ctr" if mode == "auth" else mode
        plain = _aes(m, key, iv).decryptor().update(body)
        return np.frombuffer(plain, dtype="<u2").astype(float)
    if mode == "xor_prng":
        plain = bytes(np.frombuffer(body, dtype=np.uint8) ^ _prng_stream(header8))
        return np.frombuffer(plain, dtype="<u2").astype(float)
    if mode == "dct":
        coefs = np.frombuffer(body, dtype="<i2").astype(float).reshape(-1, 8)
        return (_C8.T @ coefs.T).T.reshape(-1)
    if mode == "delta":
        return np.cumsum(np.frombuffer(body, dtype="<i2").astype(float))
    if mode == "adaptive":
        return _rice_decode(body)
    raise ValueError(mode)


# ------------------------------------------------------------------------- scene
def make_scene(rng) -> dict:
    """Four pixel vectors with a realistic shape: a decaying lamp, a pedestal, noise."""
    x = np.linspace(0, 1, N_PX)
    white = 8000 * np.exp(-2.5 * x) + 150 + rng.normal(0, 15, N_PX)
    white_dark = 150 + rng.normal(0, 3, N_PX)
    dark = 150 + rng.normal(0, 3, N_PX)
    refl = 0.5 + 0.15 * np.sin(9 * x)
    sample = (white - 150) * refl + 150 + rng.normal(0, 10, N_PX)
    clip = lambda a: np.clip(np.round(a), 0, 16383).astype(np.uint16)
    return {"sample": clip(sample), "sample_dark": clip(dark),
            "sample_white": clip(white), "sample_white_dark": clip(white_dark)}


# ------------------------------------------------------------------------- server
class SimServer:
    """``server(payload) -> list[float]`` (raises OracleError on rejection)."""

    def __init__(self, mode: str, *, binning: str = "box", permute: bool = False,
                 mask_top: bool = False, range_check: bool = False,
                 normalise: bool = False, dead: int = 0, seed: int = 0):
        assert mode in MODES
        self.mode = mode
        rng = np.random.default_rng(seed)
        self.key = bytes(rng.integers(0, 256, 16, dtype=np.uint8))
        self.B = binning_matrix(binning)
        self.perm = rng.permutation(N_PX) if permute else None
        self.mask_top, self.range_check, self.normalise = mask_top, range_check, normalise
        if dead:
            self.B[:, rng.choice(N_PX, dead, replace=False)] = 0.0
            self.B /= self.B.sum(axis=1, keepdims=True)
        self._valid: set = set()
        self.calls = 0

    def make_payload(self, rng) -> dict:
        scene = make_scene(rng)
        payload = {"device_id": "SIMULATEDDEVICE00", "i2s_tag_config": "SIM"}
        for role in _ROLES:
            pix = scene[role]
            if self.perm is not None:
                pix = pix[self.perm]               # the device emits a scrambled order
            word = int(rng.integers(0, 2**32, dtype=np.uint64))
            header8 = struct.pack("<II", 0, word)
            body = encode(self.mode, pix, header8, self.key, rng)
            assert len(body) == BODY, (self.mode, len(body))
            raw = header8 + body
            if self.mode == "auth":
                self._valid.add(bytes(raw))
            payload[role] = store.wrap_b64(raw)
        return payload

    def _pixels(self, payload: dict, role: str) -> np.ndarray:
        raw = bytes(get_blob(payload, role))
        if self.mode == "auth" and raw not in self._valid:
            raise OracleError(422, '{"error_type":"InvalidScan","extra_info":"bad_tag"}')
        pix = decode(self.mode, raw[HEADER:], raw[:HEADER], self.key)
        if self.mask_top:
            pix = np.floor(pix) % 16384
        if self.perm is not None:
            un = np.empty_like(pix)
            un[self.perm] = pix
            pix = un
        return pix

    def __call__(self, payload: dict) -> list:
        self.calls += 1
        s, d, w, wd = (self.B @ self._pixels(payload, r) for r in _ROLES)
        r = (s - d) / (w - wd)
        if self.normalise:
            r = r / np.mean(r)
        if self.range_check and (np.any(r > 12) or np.any(r < -2) or not np.all(np.isfinite(r))):
            raise OracleError(422, '{"error_type":"InvalidScan","extra_info":"low_signal"}')
        return r.tolist()
