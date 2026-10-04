"""The identifier-key gap search: each cipher path round-trips, and a planted key wins."""

import os

import numpy as np
import pytest
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from scio_offline import cipher_gap


def _blob(body: bytes) -> bytes:
    return bytes(8) + body  # 8-byte header + body, as split_blob expects


class _Rec:
    def __init__(self, sample, device):
        self.blobs = {"sample": sample}
        self.device = device


def test_every_cipher_produces_variants_of_the_right_length():
    header, body = bytes(8), bytes(range(256)) * 7  # 1792 B, like a real body
    counts = {}
    for cipher in cipher_gap.CIPHERS:
        key = os.urandom(32 if cipher == "ChaCha20" else 16)
        variants = list(cipher_gap.decrypt_variants(cipher, key, header, body))
        counts[cipher] = len(variants)
        for _label, plain in variants:
            assert isinstance(plain, bytes) and len(plain) > 0
    assert all(counts[c] > 0 for c in cipher_gap.CIPHERS), counts


def test_aptina_key_forms_cover_full_and_halves():
    forms = cipher_gap.aptina_key_forms({
        "aptinaId": "00004c8e3238c8e18032ab45611198f1",       # 16 B
        "aptina_upper": "00008e4c3832e1c8",                   # 8 B half
        "aptina_field": "328045ab1161f198",                   # 8 B half
    })
    assert all(len(k) in (16, 24, 32) for k in forms.values())
    assert any(lbl.startswith("aptina_full.") for lbl in forms)      # full id used raw
    assert any(lbl.startswith("aptina_upper.") for lbl in forms)     # upper half, new
    assert bytes.fromhex("00004c8e3238c8e18032ab45611198f1") in forms.values()


def _plant(cipher, key, bodies_plain, header=bytes(8)):
    """Encrypt known plaintexts with ``key`` so the search must recover repeatability."""
    out = []
    for plain in bodies_plain:
        if cipher == "Camellia":
            e = Cipher(algorithms.Camellia(key), modes.ECB()).encryptor()
        else:
            raise AssertionError(cipher)
        out.append(_blob(e.update(plain) + e.finalize()))
    return out


def test_planted_camellia_key_beats_random_controls():
    # Six captures of one "target": a smooth ramp with small per-scan noise, so a
    # correct decrypt is cross-scan repeatable and a wrong key is not.
    rng = np.random.default_rng(0)
    base = (np.linspace(0, 60000, 896).astype("<u2"))
    plains = [(base + rng.integers(0, 3, size=896)).astype("<u2").tobytes() for _ in range(6)]
    key = bytes.fromhex("00004c8e3238c8e18032ab45611198f1")       # the Aptina id, raw
    samples = _plant("Camellia", key, plains)
    device = {"aptinaId": "00004c8e3238c8e18032ab45611198f1", "device_id": "8032AB45611198F1"}
    records = [_Rec(s, dict(device)) for s in samples]

    report = cipher_gap.search(records, ciphers=("Camellia",), workers=4, random_count=48)
    assert report["hits"], report["top_candidates"][0]
    top = report["top_candidates"][0]
    assert "aptina" in " ".join(top["labels"]).lower()
    assert top["repeatability"] > report["random_controls"]["max"]


def test_clean_miss_on_random_bodies_reports_no_hit():
    rng = np.random.default_rng(1)
    records = [_Rec(_blob(rng.bytes(1792)), {"device_id": "8032AB45611198F1",
               "aptinaId": "00004c8e3238c8e18032ab45611198f1"}) for _ in range(6)]
    report = cipher_gap.search(records, ciphers=("TEA", "XTEA", "ARC4"), workers=4, random_count=32)
    assert report["hits"] == []
    assert "no identity-derived key" in report["conclusion"]
