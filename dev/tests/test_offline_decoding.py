"""Offline-decoding research tests (strand B): no hardware, no network.

These cover the *unresolved* attempt to decode SCiO scan blobs without the
Consumer Physics server - cipher hypotheses, firmware triage, key-candidate
search and the evidence pipeline. Nothing here is on the working scan path;
see ``dev/README.md`` for why the strand stalled.

Run with: ``pytest dev/tests/``
"""

import io
import struct
import zlib
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from scio import corpus, protocol, store
from scio_offline import (
    compression_hypothesis,
    decode,
    embedded_cipher_hypothesis,
    evidence,
    firmware,
    flashdump,
    image_codec_hypothesis,
    image_hypothesis,
    keyrecover,
    pipeline,
    repeatability,
    stream_hypothesis,
    transform_class,
    validation,
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


# --------------------------------------------------- validation harness (92 pairs)
def test_validation_harness_brackets_truth_and_noise():
    """A harness that cannot recognise a correct decode would reject a real result.

    Bracketed from both sides on the real corpus: handing it the server's own
    answer must pass at Pearson 1.0, and handing it noise must fail. Without both
    halves the harness proves nothing about any candidate it later rejects.
    """
    pairs = validation.load_pairs()
    assert len(pairs) >= 90, "expected ~92 (blobs, server spectrum) pairs on disk"
    result = validation.self_check(pairs)
    assert result["truth_passes"] is True
    assert result["truth_median_r"] == pytest.approx(1.0)
    assert result["noise_passes"] is False
    assert result["harness_ok"] is True


def test_validation_rejects_a_decoder_that_answers_on_almost_nothing():
    """Solving one lucky scan is not a decode.

    Without a coverage requirement, a decoder that answers on a single record
    would take the median of one perfect score and "pass".
    """
    pairs = validation.load_pairs()[:20]
    truth = validation.perfect_decoder(pairs)
    answered = {"n": 0}

    def only_first(blobs):
        answered["n"] += 1
        return truth(blobs) if answered["n"] == 1 else None

    rep = validation.validate(only_first, pairs)
    assert rep["answered"] == 1
    assert rep["declined"] == 19
    assert rep["gate"]["median_pearson_r"] == pytest.approx(1.0)   # the median lies
    assert rep["passed"] is False                                  # the coverage gate does not


# --------------------------------------------------- compression sweep
def test_compression_screen_excludes_transforms_that_manufacture_structure():
    """The cumulative sum of *anything* is a random walk, which scores as smooth.

    This is the same trap as random bytes read as float32, and it must be caught
    automatically rather than by remembering to blacklist it - otherwise the next
    plausible-looking transform reintroduces it.
    """
    screen = compression_hypothesis.screen_codecs(n_random=16)
    assert screen["delta_u16"]["usable"] is False
    assert screen["delta_u16"]["false_positive_rate"] > 0.5
    for codec in ("raw_deflate", "zlib", "gzip", "bz2", "lzma_auto"):
        assert screen[codec]["usable"] is True, codec
        assert screen[codec]["false_positive_rate"] == 0.0, codec
    assert "delta_u16" not in compression_hypothesis.usable_codecs(screen)


@pytest.mark.parametrize("codec,compress", [
    ("raw_deflate", lambda b: (lambda d: d.compress(b) + d.flush())(
        zlib.compressobj(9, zlib.DEFLATED, -15))),
    ("zlib", lambda b: zlib.compress(b, 9)),
    ("bz2", lambda b: __import__("bz2").compress(b)),
    ("lzma_auto", lambda b: __import__("lzma").compress(b)),
])
def test_each_codec_round_trips_a_known_stream(codec, compress):
    """A negative sweep must not be blamable on a broken decompressor."""
    plain = bytes(range(256)) * 7            # 1792 B, compressible
    assert compression_hypothesis.CODECS[codec](compress(plain)) == plain


def test_sweep_finds_compression_at_byte_and_bit_offsets():
    """Positive control: the sweep must recover a stream it is meant to find.

    Includes a 3-bit shift, because a bit-packed stream need not start on a byte
    boundary and the earlier three-decompressor test could never have found one.
    """
    x = np.linspace(0, 1, 896)
    plain = (8000 * np.exp(-4 * x)).astype("<u2").tobytes()
    d = zlib.compressobj(9, zlib.DEFLATED, -15)
    raw = d.compress(plain) + d.flush()
    live = compression_hypothesis.usable_codecs(
        compression_hypothesis.screen_codecs(n_random=8))

    def best(blob):
        hits = [h for h in compression_hypothesis.sweep_body(blob, codecs=live) if h["ok"]]
        return max(hits, key=lambda h: h["score"]) if hits else None

    at_zero = best(raw)
    assert at_zero and at_zero["codec"] == "raw_deflate"
    assert at_zero["byte_offset"] == 0 and at_zero["bit_offset"] == 0

    prefixed = best(b"\x01" * 7 + zlib.compress(plain, 9))
    assert prefixed and prefixed["byte_offset"] == 7

    shifted = best((int.from_bytes(raw, "big") >> 3).to_bytes(len(raw) + 1, "big"))
    assert shifted and shifted["bit_offset"] == 3


def test_sweep_reports_nothing_on_random_bytes():
    """The trap test: a large search over noise must stay silent."""
    rng = np.random.default_rng(7)
    live = compression_hypothesis.usable_codecs(
        compression_hypothesis.screen_codecs(n_random=8))
    for _ in range(3):
        noise = bytes(rng.integers(0, 256, 1792, dtype=np.uint8))
        assert [h for h in compression_hypothesis.sweep_body(noise, codecs=live) if h["ok"]] == []


def test_shift_bits_is_a_real_bit_shift():
    assert compression_hypothesis.shift_bits(b"\xff\x00", 0) == b"\xff\x00"
    assert compression_hypothesis.shift_bits(b"\x0f\xf0", 4) == b"\xff\x00"
    assert len(compression_hypothesis.shift_bits(bytes(1792), 3)) == 1792


def test_transform_class_cannot_report_encryption_ruled_out():
    """The verdict schema must not be able to overstate what software can show.

    No test reachable from here can exclude encryption - the device could encrypt
    and the server decrypt - so the artifact is built so that conclusion is not
    expressible, rather than merely discouraged by a comment.
    """
    rep = transform_class.run()
    assert rep["verdict"] in {"undetermined", "compression_supported", "compression_refuted"}
    assert rep["encryption"]["status"] == "not_excluded"
    assert "why_not_excludable" in rep["encryption"]
    # the size argument is the load-bearing one; assert it was actually measured
    assert rep["size_invariance"]["length_ever_depends_on_content"] is False
    for role in ("sample", "sample_dark", "sample_gradient"):
        assert rep["size_invariance"]["per_role"][role]["distinct_lengths"] in ([1792], [1648])


def test_scene_information_leaves_no_trace_in_entropy():
    """A dark frame carries far less information than a lit scene."""
    rep = transform_class.run()
    per = rep["entropy_by_scene"]["per_scene"]
    assert {"dark", "calibration_box"} <= set(per)
    assert rep["entropy_by_scene"]["mean_entropy_spread"] < 0.05


# --------------------------------------------------- image codecs
def test_stuffing_detector_fires_on_a_headerless_jpeg():
    """Positive control, and it must be the *headerless* case.

    An embedded coder would strip the JFIF container to save bytes, so the case
    that matters is the bare entropy-coded segment - which no image decoder would
    accept, and which only the byte-stuffing rule can detect. Without this control
    a negative on the corpus would prove nothing.
    """
    rng = np.random.default_rng(0)
    x = np.linspace(0, 1, 64)
    img = (200 * np.exp(-3 * x)[None, :] * np.ones((64, 1))
           + 8 * rng.standard_normal((64, 64))).clip(0, 255)
    buf = io.BytesIO()
    Image.fromarray(img.astype(np.uint8), "L").save(buf, "JPEG", quality=85)
    jpeg = buf.getvalue()
    ecs = jpeg[jpeg.index(b"\xff\xda") + 2:]          # entropy-coded segment only

    assert image_codec_hypothesis.stuffing_statistics([ecs])["jpeg"]["observed"] == 1.0
    assert image_codec_hypothesis.stuffing_statistics([ecs])["jpeg"]["consistent"] is True
    assert image_codec_hypothesis.stuffing_statistics([jpeg])["jpeg"]["consistent"] is True


def test_stuffing_detector_is_silent_on_random_bytes():
    rng = np.random.default_rng(3)
    bodies = [bytes(rng.integers(0, 256, 1792, dtype=np.uint8)) for _ in range(20)]
    st = image_codec_hypothesis.stuffing_statistics(bodies)
    for family in ("jpeg", "jpeg_ls", "jpeg2000"):
        assert st[family]["consistent"] is False, family
        assert st[family]["observed"] == pytest.approx(st[family]["random"], abs=0.05)


def test_corpus_excludes_every_standard_image_codec():
    """The real result: JPEG, JPEG-LS, JPEG 2000, and every container.

    Checked here rather than only in a report, so that a future change which makes
    the corpus look image-like cannot pass silently.
    """
    rep = image_codec_hypothesis.run()
    assert rep["verdict"] == "standard_image_codecs_excluded"
    st = rep["stuffing_statistics"]
    assert st["conclusive"] is True
    for family in ("jpeg", "jpeg_ls", "jpeg2000"):
        assert st[family]["consistent"] is False, family
    assert rep["marker_scan"]["any_excess"] is False
    assert rep["decoder_sweep"]["accepted"] == []
    assert rep["decoder_sweep"]["attempts"] >= 1000
    # no slack in which a shorter stream could hide inside the fixed buffer
    assert rep["padding_scan"]["padding_found"] is False
    assert rep["padding_scan"]["longest_constant_run"]["max"] <= 8
    # and it still may not claim the complement
    assert rep["encryption_hypothesis"] == "not_excluded"
