import struct

import numpy as np

from scio_offline import twotime as T


def _blob(word1, body):
    return struct.pack("<II", 0, word1) + bytes(body)


def test_detector_flags_reuse_and_clears_fresh_iv():
    reused = T.pair_report(T.synthetic_set(10, 1792, 1, reuse=True))
    fresh = T.pair_report(T.synthetic_set(10, 1792, 2, reuse=False))
    assert reused["reuse_suspected"] is True
    assert fresh["reuse_suspected"] is False
    assert reused["bit_distance"]["min"] < 0.10 < fresh["bit_distance"]["min"]


def test_identical_plaintext_reused_keystream_is_detected():
    # two ciphertexts of the SAME plaintext under one keystream are identical -> bitdist 0
    rng = np.random.default_rng(0)
    ks = rng.integers(0, 256, 64, dtype=np.uint8)
    plain = rng.integers(0, 256, 64, dtype=np.uint8)
    c = np.bitwise_xor(plain, ks).tobytes()
    rep = T.pair_report([c, c, c])
    assert rep["reuse_suspected"] and rep["bit_distance"]["min"] == 0.0


def test_random_bodies_sit_at_the_random_expectation():
    rng = np.random.default_rng(3)
    bodies = [rng.integers(0, 256, 1792, dtype=np.uint8).tobytes() for _ in range(8)]
    rep = T.pair_report(bodies)
    assert not rep["reuse_suspected"]
    assert 0.48 < rep["bit_distance"]["mean"] < 0.52


def test_word1_iv_check_flags_duplicates():
    rng = np.random.default_rng(5)
    b = [_blob(w, rng.integers(0, 256, 32, dtype=np.uint8)) for w in (7, 7, 9)]
    assert T.word1_iv_check(b)["word1_duplicates"] == 1


def test_header_and_body_split():
    blob = struct.pack("<II", 0, 123) + b"\xaa" * 1792
    assert T.header_words(blob) == (0, 123) and len(T.body(blob)) == 1792
