import importlib
import json
import struct
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
fw = importlib.import_module("ingest_fw151_captures")


def _blob(seed, n):
    return struct.pack("<II", 0, 1000 + seed) + bytes([seed % 256]) * (n - 8)


def _frame(payload):
    return b"\xba\x02" + struct.pack("<H", len(payload)) + payload


def _write_capture(d: Path):
    sizes = fw.EXPECT_SIZES
    frames = {role: _blob(i, sizes[role]) for i, role in enumerate(fw.ROLES)}
    blobs = []
    for i, role in enumerate(fw.ROLES):
        name = f"scan_X_{i}_{role}.bin"
        (d / name).write_bytes(frames[role])
        blobs.append({"label": role, "file": name})
    (d / "scan_X.json").write_text(json.dumps({"time": "2026-10-27 19:04:00", "blobs": blobs}))
    (d / "scan_X_raw.bin").write_bytes(b"".join(_frame(frames[r]) for r in fw.ROLES))
    for k in range(2):
        for j, role in enumerate(fw.ROLES):
            (d / f"multiscan_Y_s{k}_{role}.bin").write_bytes(_blob(10 + 3 * k + j, sizes[role]))
    (d / "multiscan_Y.json").write_text(json.dumps({"time": "2026-10-27 19:04:00", "count": 2}))
    return frames


def test_usb_stream_split_matches_frames(tmp_path):
    frames = _write_capture(tmp_path)
    assert fw.split_usb_stream((tmp_path / "scan_X_raw.bin").read_bytes()) == [frames[r] for r in fw.ROLES]


def test_parse_captures_validates_and_reports_headers(tmp_path):
    _write_capture(tmp_path)
    parsed = fw.parse_captures(tmp_path)
    assert [s["scan_id"] for s in parsed["scans"]] == ["fw151-scan-X", "fw151-multiscan_Y-s0", "fw151-multiscan_Y-s1"]
    assert parsed["scans"][0]["raw_stream_match"] is True
    assert parsed["word0_all_zero"] and parsed["word1_unique"]


def test_raw_stream_mismatch_is_refused(tmp_path):
    _write_capture(tmp_path)
    raw = bytearray((tmp_path / "scan_X_raw.bin").read_bytes())
    raw[-1] ^= 1
    (tmp_path / "scan_X_raw.bin").write_bytes(bytes(raw))
    with pytest.raises(ValueError, match="differ"):
        fw.parse_captures(tmp_path)


@pytest.mark.parametrize("raw", [b"\xba", b"\xba\x02\x03\x00xy",
                                     b"\xba\x03\x01\x00x", b"\xba\x02\x00\x00"])
def test_malformed_usb_stream_refused(raw):
    with pytest.raises(ValueError):
        fw.split_usb_stream(raw)


@pytest.mark.parametrize("change", ["duplicate", "missing", "escape", "time", "count"])
def test_bad_metadata_refused(tmp_path, change):
    _write_capture(tmp_path)
    path = tmp_path / ("multiscan_Y.json" if change == "count" else "scan_X.json")
    meta = json.loads(path.read_text())
    if change == "duplicate":
        meta["blobs"][1]["label"] = "dark"
    elif change == "missing":
        meta["blobs"].pop()
    elif change == "escape":
        meta["blobs"][0]["file"] = "../outside.bin"
    elif change == "time":
        meta["time"] = "not a timestamp"
    else:
        meta["count"] = True
    path.write_text(json.dumps(meta))
    with pytest.raises(ValueError):
        fw.parse_captures(tmp_path)


def test_multiscan_ids_include_source(tmp_path):
    _write_capture(tmp_path)
    for path in list(tmp_path.glob("multiscan_Y*")):
        (tmp_path / path.name.replace("_Y", "_Z")).write_bytes(path.read_bytes())
    ids = [s["scan_id"] for s in fw.parse_captures(tmp_path)["scans"]]
    assert len(ids) == len(set(ids)) == 5


def _replay_fixture(tmp_path, monkeypatch, live=False):
    from types import SimpleNamespace
    _write_capture(tmp_path)
    white = tmp_path / "white.json"
    white.write_text(json.dumps({"schema": "scio-wr/2",
        "device": {"device_id": "0123456789ABCDEF", "i2s_tag_config": "verified-tag"},
        "raw_hex": {fw.ROLE_WHITE[r]: _blob(4, fw.EXPECT_SIZES[r]).hex() for r in fw.ROLES}}))
    args = SimpleNamespace(device_id="0123456789abcdef", i2s="verified-tag", white=white, live=live)
    monkeypatch.setattr(fw.r, "DEV", tmp_path)
    monkeypatch.setattr(fw.session, "SCANS_DIR", tmp_path / "canonical")
    monkeypatch.setattr(fw.session, "PROCESSED_DIR", tmp_path / "spectra")
    monkeypatch.setattr(fw.time, "sleep", lambda _: None)
    return fw.parse_captures(tmp_path), args


@pytest.mark.parametrize("field,value", [("device_id", None), ("device_id", "guess"),
    ("i2s", None), ("white", None), ("i2s", "wrong"), ("device_id", "1111111111111111")])
def test_replay_requires_identity_and_calibration(tmp_path, monkeypatch, field, value):
    parsed, args = _replay_fixture(tmp_path, monkeypatch)
    setattr(args, field, value)
    with pytest.raises(ValueError):
        fw.run(parsed, args, tmp_path / "out")
    assert not (tmp_path / "out").exists()


def test_dry_run_never_authenticates_or_promotes(tmp_path, monkeypatch):
    parsed, args = _replay_fixture(tmp_path, monkeypatch)
    monkeypatch.setattr(fw.credentials, "get_token", lambda: pytest.fail("authentication in dry run"))
    monkeypatch.setattr(fw.cloud, "analyze_scan", lambda *a: pytest.fail("cloud in dry run"))
    fw.run(parsed, args, tmp_path / "out")
    assert json.loads((tmp_path / "out/run_plan.json").read_text())["planned"] == 3
    assert not (tmp_path / "canonical").exists()


@pytest.mark.parametrize("response", [{}, {"spectrum": "123"}, {"spectrum": [1] * 330},
    {"spectrum": [float("nan")] * 331}, {"spectrum": ["bad"] * 331},
    {"spectrum": [1] * 331, "wavelengths": {"steps": 0}},
    {"spectrum": [1] * 331, "wavelengths": {"start": float("inf")}}])
def test_invalid_response_never_promoted(tmp_path, monkeypatch, response):
    parsed, args = _replay_fixture(tmp_path, monkeypatch, live=True)
    monkeypatch.setattr(fw.credentials, "get_token", lambda: "fixture")
    calls = []
    monkeypatch.setattr(fw.cloud, "analyze_scan", lambda *a: calls.append(a) or response)
    fw.run(parsed, args, tmp_path / "out")
    summary = json.loads((tmp_path / "out/run_summary.json").read_text())
    assert summary["promoted"] == 0 and summary["submitted"] == 1 and len(calls) == 1
    assert not (tmp_path / "canonical").exists()


@pytest.mark.parametrize("status", [400, 401, 403, 429, 500])
def test_cloud_error_stops_batch(tmp_path, monkeypatch, status):
    parsed, args = _replay_fixture(tmp_path, monkeypatch, live=True)
    monkeypatch.setattr(fw.credentials, "get_token", lambda: "fixture")
    def fail(*args):
        raise fw.cloud.CloudError(f"HTTP {status}")
    monkeypatch.setattr(fw.cloud, "analyze_scan", fail)
    fw.run(parsed, args, tmp_path / "out")
    summary = json.loads((tmp_path / "out/run_summary.json").read_text())
    assert summary["submitted"] == 1 and summary["results"][0]["status"] == status


def test_promotion_preserves_capture_time_and_refuses_overwrite(tmp_path, monkeypatch):
    parsed, args = _replay_fixture(tmp_path, monkeypatch, live=True)
    monkeypatch.setattr(fw.credentials, "get_token", lambda: "fixture")
    monkeypatch.setattr(fw.cloud, "analyze_scan", lambda *a: {"spectrum": [1] * 331})
    fw.run(parsed, args, tmp_path / "out")
    records = list((tmp_path / "canonical").glob("*.json"))
    before = {p: p.read_bytes() for p in records + list((tmp_path / "spectra").glob("*.json"))}
    assert len(records) == 3
    assert all(json.loads(p.read_text())["sampled_at"] == "2026-10-27 19:04:00" for p in records)
    fw.run(parsed, args, tmp_path / "again")
    assert json.loads((tmp_path / "again/run_summary.json").read_text())["promoted"] == 0
    assert all(p.read_bytes() == content for p, content in before.items())


@pytest.mark.parametrize("change", ["schema", "missing_blob", "short_blob"])
def test_invalid_white_refused(tmp_path, monkeypatch, change):
    parsed, args = _replay_fixture(tmp_path, monkeypatch)
    doc = json.loads(args.white.read_text())
    if change == "schema":
        doc["schema"] = "scio-scan/1"
    elif change == "missing_blob":
        doc["raw_hex"].pop("sample_white")
    else:
        doc["raw_hex"]["sample_white"] = "00"
    args.white.write_text(json.dumps(doc))
    with pytest.raises(ValueError):
        fw.run(parsed, args, tmp_path / "out")


def test_existing_spectrum_prevents_any_raw_write(tmp_path, monkeypatch):
    _, args = _replay_fixture(tmp_path, monkeypatch)
    rec = fw.session.build_record(fw.session.annotate("test", "collision"), {}, {}, None,
                                  sampled_at="2026-10-27 19:04:00")
    spectrum = tmp_path / "spectra" / (Path(fw.session.record_filename(rec)).stem + "_spectrum.json")
    spectrum.parent.mkdir()
    spectrum.write_text("preserve")
    with pytest.raises(FileExistsError):
        fw._promote(rec, {}, [], [], {})
    assert spectrum.read_text() == "preserve"
    assert not (tmp_path / "canonical").exists()


def test_live_without_run_refused_before_parse(tmp_path, monkeypatch):
    monkeypatch.setattr(fw.r, "DEV", tmp_path)
    monkeypatch.setattr(sys, "argv", ["ingest", "--output", str(tmp_path / "out"), "--live"])
    monkeypatch.setattr(fw, "parse_captures", lambda: pytest.fail("parsed before rejecting flags"))
    with pytest.raises(SystemExit):
        fw.main()
    assert not (tmp_path / "out").exists()
