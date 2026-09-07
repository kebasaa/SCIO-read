"""Offline tests: no hardware, no network. Run with: pytest tests/"""

import struct
from pathlib import Path

import numpy as np
import pytest

from scio import corpus, decode, embedded_cipher_hypothesis, evidence, firmware, flashdump, image_hypothesis, keyrecover, pipeline, protocol, repeatability, store, stream_hypothesis
from scio.reference import inspect_reference_csv, validate_spectral_ratio
from scio.paths import portable_path

ROOT = Path(__file__).resolve().parent.parent
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


# --- protocol framing --------------------------------------------------------

def test_build_command_known_frames():
    assert protocol.build_command(protocol.Cmd.SAMPLE_SPECTRUM).hex() == "01ba020000"
    assert protocol.build_command(protocol.Cmd.READ_TEMPERATURE).hex() == "01ba040000"
    assert protocol.build_command(protocol.Cmd.SET_INDICATION_LED, b"\x00" * 9).hex() \
        == "01ba0b0900000000000000000000"
    assert protocol.build_command(protocol.Cmd.READ_FILE_HEADER, struct.pack("<I", 100)).hex() \
        == "01ba87040064000000"


def test_word_swap_and_device_id():
    assert protocol._word_swap_hex("12345678") == "34127856"


def test_parse_temperature():
    t = protocol.parse_temperature(bytes.fromhex("940100004D0A000000000000"))
    assert round(t["cmos_t"], 2) == 20.42
    assert t["chip_t"] == 26.37 and t["obj_t"] == 0.0


def test_num_responses_for_firmware():
    assert protocol.num_responses_for_firmware(120) == 2
    assert protocol.num_responses_for_firmware(147) == 3
    assert protocol.num_responses_for_firmware(160, disable_gradient=True) == 2


def test_ble_id_exposes_observed_serial_fragment():
    data = bytearray(130)
    data[40:50] = b"DF1816004A"
    data[50:56] = b"myScio"
    parsed = protocol.parse_ble_id(bytes(data))
    assert parsed["device_serial_fragment"] == "DF1816004A"
    assert parsed["device_name"] == "myScio"


# --- base64 wrapping matches what the app actually sent -----------------------

@pytest.mark.parametrize("path", FIXTURES, ids=lambda p: f"{p.parent.name}/{p.stem[-6:]}")
def test_wrap_b64_matches_app(path):
    import json
    d = json.loads(path.read_text(encoding="utf-8"))
    for k in store.SCAN_KEYS + store.WHITE_KEYS:
        if k in d.get("raw_data", {}) and k in d.get("b64_data", {}):
            raw = bytes.fromhex(d["raw_data"][k])
            assert store.wrap_b64(raw).strip().replace("\n", "") == "".join(d["b64_data"][k].split())


def test_fixtures_load():
    exs = store.load_fixtures()
    assert len(exs) == 26
    for e in exs:
        if e["spectrum"] is not None:
            assert len(e["spectrum"]) == 331


# --- blob structure ----------------------------------------------------------

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


# --- plaintext oracle --------------------------------------------------------

def test_oracle_separates_random_from_smooth():
    rng = np.random.default_rng(1)
    rand = rng.integers(0, 256, 1792, dtype=np.uint8).tobytes()
    smooth = np.clip(8000 * np.exp(-((np.arange(896) - 200) / 300.0) ** 2), 0, 65535) \
        .astype("<u2").tobytes()
    assert decode.plaintext_score(rand)["score"] < 0.2
    assert decode.plaintext_score(smooth)["score"] > 0.7


# --- firmware analysis -------------------------------------------------------

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


# --- recovery: honest negative path ------------------------------------------

def test_recover_no_hit_without_key():
    ex = store.load_fixture(next(p for p in FIXTURES if "skin" in str(p)))
    res = keyrecover.recover([ex], firmware_blobs=None)
    assert res.hits == []
    assert "firmware" in res.conclusion.lower()


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


# --- corpus, evidence and guarded output ------------------------------------

def test_corpus_index_preserves_hashes_and_spectrum_metadata(tmp_path):
    records, errors = corpus.build_corpus([ROOT / "01_rawdata" / "log_extracted"])
    assert len(records) == 26 and not errors
    out = corpus.write_index(records, tmp_path / "index.json")
    import json
    data = json.loads(out.read_text())
    assert data["schema"] == "scio-corpus-index/1"
    assert data["records"][0]["blob_sha256"]
    assert any(row["spectrum_points"] == 331 for row in data["records"])
    assert all("Users" not in row["path"] for row in data["records"])
    assert all(not Path(row["path"]).is_absolute() for row in data["records"])


def test_public_provenance_paths_do_not_disclose_home_directory(tmp_path):
    inside = ROOT / "01_rawdata" / "scan_json" / "scan_dark1.json"
    assert portable_path(inside) == "01_rawdata/scan_json/scan_dark1.json"
    assert portable_path(ROOT.parent / "private.bin") == "<external>/private.bin"


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


def test_reference_csv_axes_are_kept_separate_from_packets():
    ref = inspect_reference_csv(ROOT / "01_rawdata" / "app_researcher_output" /
                                "SCIO_scans_from_tech_support.csv")
    assert ref.rows == 145
    assert len(ref.axes["spectrum"]) == 331
    assert len(ref.axes["wr_raw"]) == 331
    assert len(ref.axes["sample_raw"]) == 331
    ratio = validate_spectral_ratio(ROOT / "01_rawdata" / "app_researcher_output" /
                                    "SCIO_scans_from_tech_support.csv")
    assert ratio["rows_tested"] == 145
    assert ratio["exact_within_1e-7_fraction"] > 0.999


# --- calibration staleness ---------------------------------------------------

def test_calibration_status_rules():
    assert store.calibration_status(None, 25.0, {"time_ms": 1, "scans": 0, "temperature": 0}) == "NEVER"
    from datetime import datetime, timedelta
    old = (datetime.now().astimezone() - timedelta(days=2)).isoformat(timespec="milliseconds")
    cal = {"meta": {"sampled_white_at": old, "scans_since_calibration": 0,
                    "temperature_before": {"cmos_t": 20.0}, "temperature_after": {"cmos_t": 20.0}}}
    assert store.calibration_status(cal, 20.0, {"time_ms": 86400000, "scans": 0, "temperature": 0}) == "TIME_THRESHOLD"
    assert store.calibration_status(cal, 20.0, {"time_ms": 0, "scans": 0, "temperature": 0}) == "NO_NEED"
    assert store.calibration_status(cal, 40.0, {"time_ms": 0, "scans": 0, "temperature": 3.0}) == "TEMP_THRESHOLD"


# --- probe safety (no hardware) ----------------------------------------------

class _FakeSerial:
    def __init__(self, canned=b""):
        self.canned = canned
        self.written = []
    def reset_input_buffer(self): pass
    def write(self, data): self.written.append(bytes(data))
    def flush(self): pass


class _FakeDev:
    SLEEP_BETWEEN_COMMANDS = 0
    def __init__(self, response=None):
        self.ser = _FakeSerial()
        self._seq = 1
        self._response = response
    def _next_seq(self):
        s = self._seq; self._seq = 1 + (self._seq % 255); return s
    def _read_response(self):
        if self._response is None:
            from scio.usb import ScioTimeout
            raise ScioTimeout("no response")
        return self._response


def test_probe_refuses_write_commands(tmp_path):
    from scio import probe
    p = probe.ScioProbe(_FakeDev(), log_dir=tmp_path)
    for opcode in (0x07, 0x81, 0x83, 0x91, 0x9A, 0x0E, 0x11, 0x0B):
        with pytest.raises(PermissionError):
            p.probe(opcode)
    # nothing should have been written to the port
    assert p.dev.ser.written == []


def test_probe_refuses_reserved_without_optin(tmp_path):
    from scio import probe
    p = probe.ScioProbe(_FakeDev(), log_dir=tmp_path)
    with pytest.raises(PermissionError):
        p.probe(0x88)                        # reserved, not opted in
    # allowed once opted in (will time out on the fake dev, which is fine)
    r = p.probe(0x88, allow_reserved=True)
    assert r.ok is False and "timeout" in r.note


def test_probe_builds_correct_frame_and_parses(tmp_path):
    from scio import probe, protocol
    resp = protocol.Response(command=0x06, length=4, data=bytes.fromhex("deadbeef"))
    p = probe.ScioProbe(_FakeDev(response=resp), log_dir=tmp_path)
    r = p.probe_event_log()
    assert p.dev.ser.written[-1].hex() == "01ba060000"   # correct 0x06 frame
    assert r.ok and r.response_len == 4 and r.response_hex == "deadbeef"
    assert list(tmp_path.glob("*.json"))                 # logged to disk


def test_probe_file_header_extended_payloads(tmp_path):
    from scio import probe
    p = probe.ScioProbe(_FakeDev(), log_dir=tmp_path)
    results = p.probe_file_header_extended(92)
    # id_only is 4 bytes; the extended ones are 12 bytes after the 5-byte header
    frames = [w.hex() for w in p.dev.ser.written]
    # seq byte varies; check protocol marker, opcode, length and payload.
    assert frames[0][2:] == "ba" + "87" + "0400" + "5c000000"   # 0x87, len 4, file id 92 LE
    assert frames[1][2:10] == "ba" + "87" + "0c00"              # 0x87, len 12 (id+off+len)
    assert len(results) == 4
