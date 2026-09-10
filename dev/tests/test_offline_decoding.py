"""Offline-decoding research tests (strand B): no hardware, no network.

These cover the *unresolved* attempt to decode SCiO scan blobs without the
Consumer Physics server - cipher hypotheses, firmware triage, key-candidate
search and the evidence pipeline. Nothing here is on the working scan path;
see ``dev/README.md`` for why the strand stalled.

Run with: ``pytest dev/tests/``
"""

import struct
from pathlib import Path

import numpy as np
import pytest

from scio import corpus, protocol, store
from scio_offline import (
    decode,
    embedded_cipher_hypothesis,
    evidence,
    firmware,
    flashdump,
    image_hypothesis,
    keyrecover,
    pipeline,
    repeatability,
    stream_hypothesis,
)

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = sorted((ROOT / "01_rawdata" / "log_extracted").glob("*/*.json"))


def test_tea_known_vector_and_xtea_roundtrip():
    zero, key = bytes(8), bytes(16)
    tea = embedded_cipher_hypothesis.tea_ecb(zero, key, decrypt=False)
    assert tea.hex() == "41ea3a0a94baa940"
    assert embedded_cipher_hypothesis.tea_ecb(tea, key) == zero
    xtea = embedded_cipher_hypothesis.xtea_ecb(zero, key, decrypt=False)
    assert embedded_cipher_hypothesis.xtea_ecb(xtea, key) == zero
def test_flashdump_exact_header_and_checksum_candidate(tmp_path):
    body = bytes([63]) * 95 + bytes([95])
    assert len(body) == 96 and flashdump.byte_sum(body) == 6080
    header = struct.pack("<IIII", 101, 96, 3, 6080)
    path = tmp_path / "dump.bin"
    path.write_bytes(bytes(37) + header + body + bytes(19))
    report = flashdump.analyze_dump(path, rolling=False)
    centers = report["files"]["centers"]
    strong = [r for r in centers["candidates"] if r["confidence"] == "strong"]
    assert len(strong) == 1 and strong[0]["offset"] == 53
    assert flashdump.compare_dumps([path, path])["identical"] is True
def test_blob_header_and_block_multiple():
    ex = store.load_fixture(next(p for p in FIXTURES if "skin" in str(p)))
    b = decode.split_blob(ex["blobs"]["sample"])
    assert b.type == protocol.BLOB_TYPE_SAMPLE
    assert len(b.body) % 16 == 0
    g = decode.split_blob(ex["blobs"]["sample_gradient"])
    assert g.type == protocol.BLOB_TYPE_GRADIENT
    assert len(g.body) % 16 == 0
def test_second_header_word_is_unclassified_alias():
    ex = store.load_fixture(FIXTURES[0])
    parsed = protocol.parse_blob_header(ex["blobs"]["sample"])
    assert parsed["second_word"] == parsed["nonce"]
def test_oracle_separates_random_from_smooth():
    rng = np.random.default_rng(1)
    rand = rng.integers(0, 256, 1792, dtype=np.uint8).tobytes()
    smooth = np.clip(8000 * np.exp(-((np.arange(896) - 200) / 300.0) ** 2), 0, 65535) \
        .astype("<u2").tobytes()
    assert decode.plaintext_score(rand)["score"] < 0.2
    assert decode.plaintext_score(smooth)["score"] > 0.7
def test_signature_scan_finds_sbox():
    blob = bytes(256) + keyrecover._AES_SBOX_HEAD + bytes(256)
    assert keyrecover.find_signatures(blob).get("AES_SBOX") == [256]
def test_parse_ldr_accepts_synthetic_and_rejects_random():
    # one FIRST+FINAL block, 16 payload bytes
    code = (0xAD << 24) | 0x8000 | 0x4000
    block = struct.pack("<IIII", code, 0xFFA00000, 16, 0) + bytes(16)
    assert firmware.parse_ldr(block)["valid_ldr"] is True
    rng = np.random.default_rng(2)
    assert firmware.parse_ldr(rng.integers(0, 256, 4096, dtype=np.uint8).tobytes())["valid_ldr"] is False
def test_decode_blob_strips_checksum():
    import base64
    body = bytes(range(32))
    b64 = base64.b64encode(struct.pack("<I", 0xDEADBEEF) + body).decode()
    dec = firmware.decode_blob(b64)
    assert dec["checksum"] == 0xDEADBEEF and dec["data"] == body
def test_recover_wrong_firmware_reports_triage():
    ex = store.load_fixture(next(p for p in FIXTURES if "skin" in str(p)))
    rng = np.random.default_rng(3)
    fake = {"dsp_op": {"data": rng.integers(0, 256, 2400, dtype=np.uint8).tobytes()}}
    res = keyrecover.recover([ex], firmware_blobs=fake, device={"device_id": "8032AB45611198F1"})
    assert res.hits == []
    assert "dsp_op" in res.firmware_triage
    assert res.firmware_triage["dsp_op"]["verdict"].startswith("high-entropy")
def test_identifier_candidates_include_serial_ids_versions_and_combinations():
    candidates = keyrecover.candidate_keys_from_device({
        "device_id": "8032AB45611198F1", "dsp_id": "e24da26b2304c2c0",
        "ble_id": "01665900004c99b4", "serial_number": "SCIO-1234",
        "firmware_version": 147, "i2s_tag_config": "20150812-e:PRODUCTION",
    })
    assert any(name.startswith("serial.") for name in candidates)
    assert any(name.startswith("device_id+") and "firmware_version" in name for name in candidates)
    assert all(len(key) in (16, 24, 32) for key in candidates.values())
def test_no_arbitrary_firmware_windows_without_cipher_signature():
    assert keyrecover.candidate_keys_from_firmware(bytes(range(255)), {}) == {}
def test_evidence_report_is_hypothesis_neutral():
    records, _ = corpus.build_corpus([FIXTURES[0]])
    report = evidence.corpus_report(records)
    assert report["interpretation"]["status"] == "unresolved"
    assert set(report["interpretation"]["compatible_hypotheses"]) == {
        "packed/structured", "compressed", "obfuscated", "encrypted"}
    assert report["blobs"][0]["body_multiple_16"]
    assert {x["view"] for x in evidence.screen_layouts(records[0].blobs["sample"])}.issuperset(
        {"u16le", "u16be", "u32le", "u32be", "u12le", "u12be"})
def test_image_hypothesis_requires_structure_and_repeatability():
    rng = np.random.default_rng(7)
    random_blob = b"\x00" * 8 + rng.integers(0, 256, 1792, dtype=np.uint8).tobytes()
    assert image_hypothesis.file_signature(random_blob) is None
    assert (28, 32) in image_hypothesis.factor_shapes(896)
    metric = image_hypothesis.spatial_metrics(np.arange(896), (28, 32))
    assert metric["spatial_score"] > 0.9
def test_stream_generators_are_deterministic_and_reversible():
    body = bytes(range(128))
    for kind in ("lcg_nr", "lcg_glibc", "lcg_msvc", "xorshift32", "mt19937", "sha256_counter"):
        stream = stream_hypothesis.keystream(12345, len(body), kind)
        transformed = bytes(a ^ b for a, b in zip(body, stream))
        assert bytes(a ^ b for a, b in zip(transformed, stream)) == body
def test_repeatability_oracle_separates_related_plaintext():
    rng = np.random.default_rng(9)
    base = np.arange(896, dtype="<u2")
    related = np.clip(base + rng.integers(0, 3, base.size), 0, 65535).astype("<u2")
    random = rng.integers(0, 65536, base.size, dtype=np.uint16).astype("<u2")
    assert repeatability.plaintext_repeatability(base.tobytes(), related.tobytes())["score"] > 0.99
    assert repeatability.plaintext_repeatability(base.tobytes(), random.tobytes())["score"] < 0.2
def test_pipeline_refuses_unvalidated_decoder():
    profile = pipeline.DecoderProfile("test", "1", "device", None, "report.json", validated=False)
    with pytest.raises(RuntimeError, match="not validated"):
        pipeline.make_spectrum(np.arange(331), profile=profile)
def test_pipeline_exports_only_validated_spectrum(tmp_path):
    profile = pipeline.DecoderProfile("synthetic-test", "1", "device", None,
                                      "synthetic fixture", validated=True)
    spectrum = pipeline.make_spectrum(np.linspace(1, 2, 331), profile=profile)
    out = pipeline.export_spectrum(spectrum, tmp_path / "spectrum.csv")
    assert out.read_text().splitlines()[0].startswith("wavelength_nm,normalized")
