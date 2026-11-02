import importlib
import sys
import zlib
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
probe = importlib.import_module("probe_application_zero_keys")


def test_zero_and_uuid_candidates_are_distinct_and_explicit():
    keys = probe.candidates()
    for size in (16, 24, 32):
        assert bytes(size) in keys
        assert b"0" * size in keys
        assert bytes(size) != b"0" * size
    assert probe.uuid.UUID(probe.PUBLIC_UUID).bytes in keys
    assert probe.uuid.UUID(probe.PUBLIC_UUID).bytes_le in keys
    assert all(len(key) in (16, 24, 32) for key in keys)


def test_correct_zero_and_uuid_keys_recover_compressed_data():
    assert probe.positive_controls()["configurations_recovered"] == 120


@pytest.mark.parametrize("wbits", [15, 31, -15])
def test_codec_oracle_rejects_partial_or_arbitrary_trailing_data(wbits):
    compressor = zlib.compressobj(wbits=wbits)
    packed = compressor.compress(bytes(range(256)) * 4) + compressor.flush()
    assert probe.unpack(packed, wbits)["padding"] == "none"
    assert probe.unpack(packed + b"\0\0", wbits)["padding"] == "zero"
    assert probe.unpack(packed + b"\x03" * 3, wbits)["padding"] == "pkcs7"
    assert probe.unpack(packed[:-1], wbits) is None
    assert probe.unpack(packed + b"garbage", wbits) is None


def test_expansion_and_small_accidental_streams_are_rejected():
    assert probe.unpack(zlib.compress(bytes(probe.CAP + 1)), 15) is None
    assert probe.unpack(zlib.compress(b"short"), 15) is None


def test_misaligned_ciphertext_is_never_silently_truncated():
    with pytest.raises(ValueError, match="refusing truncation"):
        probe.decrypt_candidate(bytes(31), bytes(16), 8, "CBC", "zero")


@pytest.mark.parametrize("key", [bytes(16), probe.uuid.UUID(probe.PUBLIC_UUID).bytes])
def test_repeatability_detects_known_key_with_uncompressed_signal(key):
    rng = probe.np.random.default_rng(23)
    base = rng.integers(1000, 30000, 256)
    blobs = []
    for index in range(4):
        signal = (base + rng.integers(-3, 4, 256)).astype("<u2").tobytes()
        enc = probe.Cipher(probe.algorithms.AES(key), probe.modes.ECB()).encryptor()
        blobs.append(bytes(4) + index.to_bytes(4, "little") + enc.update(signal) + enc.finalize())
    assert probe.verify_repeatability(blobs, key)["repeatability"] > .99
    assert probe.verify_repeatability(blobs, b"wrong fixture key"[:16])["repeatability"] < .5
