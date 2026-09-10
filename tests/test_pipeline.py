"""Offline tests for the working pipeline: no hardware, no network.

Covers the protocol, the transports' pure parts, the canonical scan store,
white-reference/calibration policy, credentials and the cloud request builder.
Offline-decoding research is tested separately in ``dev/tests/``.

Run with: ``pytest tests/``
"""

import struct
from pathlib import Path

import pytest

from scio import corpus, logscan, protocol, session, store
from scio.reference import inspect_reference_csv, validate_spectral_ratio
from scio.paths import portable_path

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = sorted((ROOT / "01_rawdata" / "log_extracted").glob("*/*.json"))


def test_build_command_known_frames():
    assert protocol.build_command(protocol.Cmd.SAMPLE_SPECTRUM).hex() == "01ba020000"
    assert protocol.build_command(protocol.Cmd.READ_TEMPERATURE).hex() == "01ba040000"
    assert protocol.build_command(protocol.Cmd.SET_INDICATION_LED, b"\x00" * 9).hex() \
        == "01ba0b0900000000000000000000"
    assert protocol.build_command(protocol.Cmd.READ_FILE_HEADER, struct.pack("<I", 100)).hex() \
        == "01ba87040064000000"


def test_word_swap_and_device_id():
    assert protocol._word_swap_hex("12345678") == "34127856"


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


@pytest.mark.parametrize("path", FIXTURES[:3], ids=lambda p: f"{p.parent.name}/{p.stem[-6:]}")
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


def test_calibration_status_rules():
    assert store.calibration_status(None, 25.0, {"time_ms": 1, "scans": 0, "temperature": 0}) == "NEVER"
    from datetime import datetime, timedelta
    old = (datetime.now().astimezone() - timedelta(days=2)).isoformat(timespec="milliseconds")
    cal = {"meta": {"sampled_white_at": old, "scans_since_calibration": 0,
                    "temperature_before": {"cmos_t": 20.0}, "temperature_after": {"cmos_t": 20.0}}}
    assert store.calibration_status(cal, 20.0, {"time_ms": 86400000, "scans": 0, "temperature": 0}) == "TIME_THRESHOLD"
    assert store.calibration_status(cal, 20.0, {"time_ms": 0, "scans": 0, "temperature": 0}) == "NO_NEED"
    assert store.calibration_status(cal, 40.0, {"time_ms": 0, "scans": 0, "temperature": 3.0}) == "TEMP_THRESHOLD"


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


def test_credentials_roundtrip_and_tamper(tmp_path):
    from scio import credentials as cr
    p = tmp_path / "creds.enc"
    cr.save_credentials("me@example.com", "hunter2", path=p)
    raw = p.read_bytes()
    assert b"hunter2" not in raw and b"me@example.com" not in raw   # encrypted at rest
    assert cr.load_credentials(path=p) == ("me@example.com", "hunter2")
    p.write_bytes(raw[:-3] + b"xyz")                                # tamper
    assert cr.load_credentials(path=p) is None
    assert cr.clear_credentials(path=p) is True
    assert cr.load_credentials(path=p) is None


def test_build_scan_payload_has_all_server_fields():
    from scio import store, cloud
    sc = store.load_scan("01_rawdata/scan_json/scan_20260907_hand.json")
    wr = store.load_latest_calibration("8032AB45611198F1")
    p = cloud.build_scan_payload(sc, wr, sc["device"]["device_id"], sc["device"]["i2s_tag_config"])
    required = {"device_id", "sampled_at", "sampled_white_at", "scio_edition",
                "i2s_tag_config", "mobile_mac_address", "widget_scan_attributes",
                "sample", "sample_dark", "sample_gradient",
                "sample_white", "sample_white_dark", "sample_white_gradient"}
    assert required <= set(p)
    import base64
    assert len(base64.b64decode(p["sample"])) == 1800
_WR_DEV = {"device_id": "DEVTEST", "i2s_tag_config": "20150812-e:PRODUCTION",
           "firmware_version": 147}
_WR_TB = {"cmos_t": 20.42, "cmos_t_app": 19.0, "chip_t": 26.3, "obj_t": 0.0, "raw_u32": [404, 2630, 0]}
_WR_TA = {"cmos_t": 21.0, "cmos_t_app": 20.0, "chip_t": 26.5, "obj_t": 0.0, "raw_u32": [405, 2650, 0]}
_WR_BLOBS = {"sample_white": b"\x00" * 1800, "sample_white_dark": b"\x01" * 1800,
             "sample_white_gradient": b"\x02" * 1656}


def test_calibration_files_are_never_overwritten(tmp_path):
    p1 = store.save_calibration(_WR_BLOBS, _WR_DEV, _WR_TB, _WR_TA, out_dir=tmp_path, stamp="20260910_1200")
    p2 = store.save_calibration(_WR_BLOBS, _WR_DEV, _WR_TB, _WR_TA, out_dir=tmp_path, stamp="20260910_1200")
    p3 = store.save_calibration(_WR_BLOBS, _WR_DEV, _WR_TB, _WR_TA, out_dir=tmp_path, stamp="20260910_1300")
    # user-requested naming scheme, with a collision suffix instead of an overwrite
    assert p1.name == "20260910_1200_calibration.json"
    assert p2.name == "20260910_1200_calibration_2.json"
    assert all(p.exists() for p in (p1, p2, p3))
    import json as _json
    assert _json.loads(p1.read_text())["wr_id"] != _json.loads(p2.read_text())["wr_id"]
    # timestamp is inside the file too
    assert _json.loads(p1.read_text())["file_timestamp"] == "20260910_1200"
    # "latest" is computed, not an overwritten copy
    assert store.latest_calibration_path("DEVTEST", wr_dir=tmp_path).name == p3.name
    assert len(store.list_calibrations("DEVTEST", wr_dir=tmp_path)) == 3


def test_bump_scans_only_touches_newest_and_trips_limit(tmp_path):
    import json as _json
    old = store.save_calibration(_WR_BLOBS, _WR_DEV, _WR_TB, _WR_TA, out_dir=tmp_path, stamp="20260910_1200")
    store.save_calibration(_WR_BLOBS, _WR_DEV, _WR_TB, _WR_TA, out_dir=tmp_path, stamp="20260910_1300")
    for _ in range(3):
        n = store.bump_scans_since_calibration("DEVTEST", wr_dir=tmp_path)
    assert n == 3
    assert _json.loads(old.read_text())["scans_since_calibration"] == 0   # history untouched
    cal = store.load_latest_calibration("DEVTEST", wr_dir=tmp_path)
    assert store.calibration_status(cal, 19.5, {"time_ms": 0, "scans": 3, "temperature": 0}) == "EXCEED_SCANS_LIMIT"
    assert store.calibration_status(cal, 19.5, {"time_ms": 0, "scans": 4, "temperature": 0}) == "NO_NEED"


def test_real_server_thresholds_disable_every_rule(tmp_path):
    """Live values (2026-09): 1e9 min / 1e9 scans / 10000 C => only NEVER can fire."""
    store.save_calibration(_WR_BLOBS, _WR_DEV, _WR_TB, _WR_TA, out_dir=tmp_path, stamp="20260910_1200")
    cal = store.load_latest_calibration("DEVTEST", wr_dir=tmp_path)
    real = {"time_ms": 1_000_000_000 * 60 * 1000, "scans": 1_000_000_000, "temperature": 10000.0}
    assert store.calibration_status(cal, 60.0, real) == "NO_NEED"
    assert store.calibration_status(None, 60.0, real) == "NEVER"


def test_calibration_report_carries_supporting_numbers(tmp_path):
    store.save_calibration(_WR_BLOBS, _WR_DEV, _WR_TB, _WR_TA, out_dir=tmp_path, stamp="20260910_1200")
    cal = store.load_latest_calibration("DEVTEST", wr_dir=tmp_path)
    rep = store.calibration_report(cal, 25.0, {"time_ms": 0, "scans": 0, "temperature": 0})
    assert rep["status"] == "NO_NEED"
    assert rep["wr_temperature"] == 19.5           # mean of the app-truncated Aptina values
    assert rep["temp_delta"] == 5.5
    assert rep["wr_age_ms"] is not None and rep["scans_since_calibration"] == 0
    assert rep["wr_id"]


def test_threshold_cache_roundtrip(tmp_path):
    p = tmp_path / "thr.json"
    store.cache_thresholds("DEVTEST", {"time_ms": 1, "scans": 2, "temperature": 3.0, "source": "server"}, path=p)
    got = store.load_cached_thresholds("DEVTEST", path=p)
    assert got["scans"] == 2 and got["source"] == "cache"
    assert store.load_cached_thresholds("NOPE", path=p) is None


def test_app_truncated_temperature_matches_java():
    """Java: (long)((float)((long)((double)raw - 375.22)) / 1.4092f) - truncates twice."""
    for raw in (404, 432, 400, 1000, 376):
        expected = float(int(float(int(raw - 375.22)) / 1.4092))
        t = protocol.parse_temperature(struct.pack("<3I", raw, 2637, 0))
        assert t["cmos_t_app"] == expected
        assert t["raw_u32"][0] == raw
    # the exact float and the app value genuinely differ (404 -> 20.42 vs 19)
    t = protocol.parse_temperature(struct.pack("<3I", 404, 2637, 0))
    assert round(t["cmos_t"], 2) == 20.42 and t["cmos_t_app"] == 19.0


# --------------------------------------------------------------------- session
# A fake device: enough of the ScioUSB surface for session.capture, no hardware.
class _FakeScio:
    def __init__(self):
        self.temps = []
        self.scans = 0

    def read_device_info(self):
        return {"device_id": "FAKEDEV0000CAFE", "i2s_tag_config": "20150812-e:PRODUCTION",
                "firmware_version": 147, "dsp_id": "deadbeef"}

    def read_temperature(self):
        self.temps.append(len(self.temps))
        return {"cmos_t": 20.4, "cmos_t_app": 19.0, "chip_t": 30.0, "obj_t": 0.0,
                "raw_u32": [404, 3000, 0]}

    def _blobs(self, seed):
        return {"sample": bytes([seed] * 1800), "sample_dark": bytes([seed + 1] * 1800),
                "sample_gradient": bytes([seed + 2] * 1656)}

    def sample_spectrum(self, fw=0, disable_gradient=False):
        self.scans += 1
        return {"blobs": self._blobs(self.scans), "status_word": 0, "n_responses": 3}

    def white_reference(self, fw=0, disable_gradient=False):
        b = self._blobs(200)
        return {"sample_white": b["sample"], "sample_white_dark": b["sample_dark"],
                "sample_white_gradient": b["sample_gradient"]}


def _capture(tmp_path, **kw):
    """Capture with every path pointed at tmp_path: nothing under 01_rawdata is touched."""
    dev = _FakeScio()
    path = session.capture(dev, "fake target", "id-1", "a comment",
                           out_dir=tmp_path / "scans", wr_dir=tmp_path / "wr",
                           thresholds=dict(session.THRESHOLDS_FALLBACK), **kw)
    return dev, path


def test_capture_needs_no_network_and_writes_a_complete_record(tmp_path):
    prompted = []
    dev, path = _capture(tmp_path, on_calibration_needed=lambda rep: prompted.append(rep) or True)
    rec = session.load_record(path)
    # No white reference existed, so one had to be taken first: status NEVER.
    assert prompted and prompted[0]["status"] == "NEVER"
    assert rec["schema"] == "scio-scan/2"
    assert rec["annotation"] == {"name": "fake target", "scan_id": "id-1", "comment": "a comment"}
    assert rec["sampled_at"] and rec["scan_uid"]
    assert set(rec["raw"]) == {"sample", "sample_dark", "sample_gradient"}
    assert set(rec["white_reference"]["blobs"]) == {"sample_white", "sample_white_dark",
                                                    "sample_white_gradient"}
    assert rec["temperature"]["scan_before"] and rec["temperature"]["scan_after"]
    assert rec["calibration"]["thresholds_source"] == "fallback"
    # everything the server needs, straight out of the record
    payload = session.to_payload(rec)
    assert set(payload) >= {"device_id", "sampled_at", "sampled_white_at", "i2s_tag_config",
                            "mobile_mac_address", "sample", "sample_dark", "sample_white",
                            "sample_white_dark", "scio_edition", "widget_scan_attributes"}
    assert payload["mobile_mac_address"] == "02:00:00:00:00:00"


def test_capture_refuses_when_the_white_reference_is_declined(tmp_path):
    with pytest.raises(RuntimeError, match="white reference required"):
        _capture(tmp_path, on_calibration_needed=lambda rep: False)


def test_annotation_requires_a_name_and_invents_a_scan_id():
    with pytest.raises(ValueError):
        session.annotate("   ")
    a = session.annotate("bark")
    assert a["scan_id"] and a["comment"] == ""


def test_record_blobs_roundtrip_through_both_encodings():
    blobs = {"sample": bytes(range(256)) * 7, "sample_dark": b"\x00" * 1800}
    rec = session.build_record(session.annotate("x"), {"device_id": "D", "i2s_tag_config": "t"},
                               blobs, None)
    back, _ = session.record_blobs(rec)
    assert back == blobs
    for entry in rec["raw"].values():
        # standard base64, wrapped like the app - never URL-safe, which the server rejects
        assert "-" not in entry["b64"] and "_" not in entry["b64"]
        assert store.blob_bytes({"b64": entry["b64"]}) == bytes.fromhex(entry["hex"])


def test_to_payload_rejects_a_record_the_server_would_reject():
    blobs = {"sample": b"\x00" * 1800, "sample_dark": b"\x00" * 1800}
    white = {"blobs": {"sample_white": store.blob_entry(b"\x01" * 1800),
                       "sample_white_dark": store.blob_entry(b"\x02" * 1800)},
             "sampled_white_at": "2026-01-01T00:00:00.000+01:00"}
    rec = session.build_record(session.annotate("x"), {"device_id": "D", "i2s_tag_config": ""},
                               blobs, white)
    with pytest.raises(ValueError, match="i2s_tag_config"):
        session.to_payload(rec)
    rec["device"]["i2s_tag_config"] = "20150812-e:PRODUCTION"
    assert session.to_payload(rec)["i2s_tag_config"] == "20150812-e:PRODUCTION"
    rec["white_reference"]["blobs"].pop("sample_white")
    with pytest.raises(ValueError, match="missing blobs"):
        session.to_payload(rec)


def test_legacy_conversion_copies_only_and_fixes_each_group(tmp_path):
    """Convert the real corpus into a temp dir: 01_rawdata must not be touched."""
    import hashlib
    def digest():
        return {p: hashlib.sha256(p.read_bytes()).hexdigest()
                for p in sorted((ROOT / "01_rawdata").rglob("*.json"))}

    before = digest()
    written = session.convert_legacy(out_dir=tmp_path / "scans")
    assert digest() == before, "conversion must never modify or delete an original capture"
    assert len(written) >= 80

    recs = [session.load_record(p) for p in written]
    for rec in recs:
        assert rec["annotation"]["name"] and rec["annotation"]["scan_id"]
        assert rec["sampled_at"]
        scan_b, white_b = session.record_blobs(rec)
        assert len(scan_b["sample"]) == 1800 and len(white_b["sample_white"]) == 1800
        assert (rec["device"].get("i2s_tag_config") or "").strip()

    g2023 = [r for r in recs if "2023" in r["provenance"]["source"]]
    assert len(g2023) == 18
    for rec in g2023:
        # device_id was absent in 2023 and must be derived UPPERCASE (lowercase -> HTTP 404)
        assert rec["device"]["device_id"] == "8032AB45611198F1"
        assert rec["sampled_at"].endswith("+02:00")      # naive local time got an offset
        assert any("PHYSICALLY INVALID" in n for n in rec["provenance"]["notes"])

    fixed = [r for r in recs
             if any("i2s_tag_config was empty" in n for n in r["provenance"]["notes"])]
    assert len(fixed) == 30


def test_conversion_is_idempotent(tmp_path):
    out = tmp_path / "scans"
    first = session.convert_legacy(out_dir=out)
    assert session.convert_legacy(out_dir=out) == []
    assert len(list(out.glob("*.json"))) == len(first)


def test_log_parser_recovers_more_scans_than_were_ever_extracted():
    """The old notebook dropped scans the server never answered; these are them."""
    scans = logscan.parse_logs(ROOT / "01_rawdata" / "log_files")
    assert len(scans) == 43 and len(FIXTURES) == 26
    for s in scans:
        scan_b, white_b = logscan.blobs_from_request(s["request"])
        assert len(scan_b["sample"]) == 1800 and len(white_b["sample_white"]) == 1800
        # the independently reassembled wire bytes must agree with what the app sent
        for k, hex_str in s["wire_hex"].items():
            assert bytes.fromhex(hex_str) == scan_b[k]
    assert any(s["spectrum"] is None for s in scans)


def test_extract_logs_skips_scans_already_present(tmp_path):
    out = tmp_path / "scans"
    session.convert_legacy(out_dir=out)               # brings in the 26 extracted fixtures
    new = session.extract_logs(out_dir=out)
    assert len(new) == 17                             # 43 logged - 26 already extracted
    assert session.extract_logs(out_dir=out) == []


def test_pending_selects_only_unprocessed_scans(tmp_path):
    scans, processed = tmp_path / "scans", tmp_path / "out"
    scans.mkdir()
    processed.mkdir()
    for i in range(3):
        rec = session.build_record(session.annotate(f"s{i}", f"id{i}"),
                                   {"device_id": "D", "i2s_tag_config": "t"},
                                   {"sample": b"\x00" * 1800, "sample_dark": b"\x01" * 1800}, None)
        session.write_record(rec, scans)
    todo = session.pending(scans, processed)
    assert len(todo) == 3
    (processed / (todo[0].stem + "_spectrum.json")).write_text("{}", encoding="utf-8")
    assert [p.name for p in session.pending(scans, processed)] == [p.name for p in todo[1:]]


def test_process_pending_records_failures_without_stopping(tmp_path, monkeypatch):
    import json as _json
    scans, processed = tmp_path / "scans", tmp_path / "out"
    scans.mkdir()
    processed.mkdir()
    good = session.build_record(
        session.annotate("good", "g"), {"device_id": "D", "i2s_tag_config": "t"},
        {"sample": b"\x00" * 1800, "sample_dark": b"\x01" * 1800},
        {"sampled_white_at": "2026-01-01T00:00:00.000+01:00",
         "blobs": {"sample_white": store.blob_entry(b"\x02" * 1800),
                   "sample_white_dark": store.blob_entry(b"\x03" * 1800)}})
    bad = session.build_record(session.annotate("bad", "b"), {"device_id": "D"},
                               {"sample": b"\x00" * 1800}, None)
    session.write_record(good, scans)
    session.write_record(bad, scans)

    calls = []
    monkeypatch.setattr(session.cloud, "analyze_scan",
                        lambda tok, payload: calls.append(tok) or {"spectrum": [0.5] * 331})
    rows = session.process_pending(token=lambda: f"tok{len(calls)}", scans_dir=scans,
                                   processed_dir=processed)
    assert len(rows) == 2
    ok = [r for r in rows if r["error"] is None]
    assert len(ok) == 1 and calls == ["tok0"]         # a fresh token is fetched per scan
    assert any("missing blobs" in (r["error"] or "") for r in rows)

    out = _json.loads((processed / Path(ok[0]["processed"]).name).read_text(encoding="utf-8"))
    assert out["schema"] == "scio-spectrum/1"
    assert out["spectrum"]["n_points"] == 331 and out["spectrum"]["range_nm"] == [740, 1070]
    assert out["scan"]["annotation"]["name"] == "good"   # the record travels with the result
    assert (processed / (Path(ok[0]["processed"]).stem + ".csv")).exists()
    assert len(session.pending(scans, processed)) == 1
