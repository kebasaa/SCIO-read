import json
import subprocess
from types import SimpleNamespace

import pytest

from scio import cloud, location, session

FIX = {"latitude": 47.3769, "longitude": 8.5417, "source": "unit-test", "accuracy_m": 25.0,
       "altitude_m": None}


class _Dev:
    def __init__(self):
        self.scans = 0

    def read_device_info(self):
        return {"device_id": "FAKEDEV0000CAFE", "i2s_tag_config": "20150812-e:PRODUCTION",
                "firmware_version": 147}

    def read_temperature(self):
        return {"cmos_t": 20.4, "cmos_t_app": 19.0, "chip_t": 30.0, "obj_t": 0.0}

    def sample_spectrum(self, fw=0):
        self.scans += 1
        return {"blobs": {"sample": b"\1" * 1800, "sample_dark": b"\2" * 1800}, "status_word": 0}

    def white_reference(self, fw=0):
        return {"sample_white": b"\3" * 1800, "sample_white_dark": b"\4" * 1800}


def _capture(tmp_path, **kw):
    dev = _Dev()
    path = session.capture(dev, "loc", "id-1", out_dir=tmp_path / "scans", wr_dir=tmp_path / "wr",
                           thresholds=dict(session.THRESHOLDS_FALLBACK),
                           on_calibration_needed=lambda rep: True, **kw)
    return dev, session.load_record(path)


@pytest.fixture
def with_fix(monkeypatch):
    monkeypatch.setattr(location, "get_fix", lambda timeout=10.0: (dict(FIX), []))


def test_capture_records_location_locally_and_never_sends_it_by_default(tmp_path, with_fix):
    _, rec = _capture(tmp_path)
    assert rec["mobile_GPS"]["latitude"] == FIX["latitude"]
    assert rec["mobile_GPS"]["longitude"] == FIX["longitude"]
    assert set(rec["mobile_GPS"]) == set(location.GPS_KEYS)
    assert rec["location_meta"]["source"] == "unit-test" and rec["location_meta"]["enabled"]
    assert rec["location_meta"]["sent_to_server"] is False
    assert "mobile_GPS" not in session.to_payload(rec)
    assert "mobile_GPS" not in session.to_payload(rec, send_location="yes")   # only True is consent
    assert session.to_payload(rec, send_location=True)["mobile_GPS"]["latitude"] == FIX["latitude"]


def test_no_fix_leaves_fields_empty_and_capture_succeeds(tmp_path):
    _, rec = _capture(tmp_path)
    assert rec["mobile_GPS"] == location.empty_gps()
    assert rec["location_meta"]["notes"] == ["stubbed in tests"]
    assert "mobile_GPS" not in session.to_payload(rec, send_location=True)


def test_geolocation_can_be_switched_off(tmp_path, with_fix, monkeypatch):
    _, rec = _capture(tmp_path, geolocate=False)
    assert rec["mobile_GPS"] == location.empty_gps() and not rec["location_meta"]["enabled"]
    monkeypatch.setenv(location.ENV_SWITCH, "0")
    _, rec = _capture(tmp_path)
    assert rec["mobile_GPS"]["latitude"] is None


def test_manual_location_wins_and_bad_manual_fails_before_scanning(tmp_path, with_fix):
    _, rec = _capture(tmp_path, location_override={"latitude": 46.0, "longitude": 7.0,
                                                    "locality": "Somewhere"})
    assert rec["mobile_GPS"]["latitude"] == 46.0 and rec["mobile_GPS"]["locality"] == "Somewhere"
    assert rec["location_meta"]["source"] == "manual"
    dev = _Dev()
    with pytest.raises(ValueError):
        session.capture(dev, "x", out_dir=tmp_path / "s2", wr_dir=tmp_path / "w2",
                        thresholds=dict(session.THRESHOLDS_FALLBACK),
                        on_calibration_needed=lambda rep: True,
                        location_override={"latitude": 200, "longitude": 0})
    assert dev.scans == 0


def test_processed_spectrum_keeps_location_and_consent_controls_sending(tmp_path, with_fix, monkeypatch):
    sent = []
    monkeypatch.setattr(cloud, "analyze_scan", lambda token, payload: sent.append(payload) or {"spectrum": [1.0]})
    monkeypatch.setattr(cloud, "spectrum_from_response", lambda resp: ([740], [1.0]))
    _capture(tmp_path)
    raw = next((tmp_path / "scans").glob("*.json"))
    out = json.loads(session.process(raw, "tok", tmp_path / "p1").read_text())
    assert "mobile_GPS" not in sent[-1]
    assert out["location"]["mobile_GPS"]["latitude"] == FIX["latitude"]
    assert out["location"]["sent_to_server"] is False
    out = json.loads(session.process(raw, "tok", tmp_path / "p2", send_location=True).read_text())
    assert sent[-1]["mobile_GPS"]["longitude"] == FIX["longitude"]
    assert out["location"]["sent_to_server"] is True


def test_legacy_record_without_location_has_empty_fields():
    rec = session.build_record({"name": "n", "scan_id": "i", "comment": ""}, {}, {}, None)
    assert rec["mobile_GPS"] == location.empty_gps()
    assert rec["location_meta"]["enabled"] is False


def test_powershell_provider_parses_fix_and_denial(monkeypatch):
    monkeypatch.setattr(location.shutil, "which", lambda name: "powershell.exe")
    reply = {"unknown": False, "latitude": 47.0, "longitude": 8.0, "accuracy_m": 30.0,
             "permission": "Granted", "status": "Ready"}
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: SimpleNamespace(stdout=json.dumps(reply)))
    fix, note = location._windows_powershell(1)
    assert fix["latitude"] == 47.0 and fix["accuracy_m"] == 30.0 and note is None
    reply = {"unknown": True, "permission": "Denied", "status": "Disabled"}
    fix, note = location._windows_powershell(1)
    assert fix is None and "Denied" in note


def test_invalid_or_null_island_coordinates_are_rejected():
    assert location._fix(0, 0, "x") is None
    assert location._fix(91, 0, "x") is None
    assert location._fix("nan?", 1, "x") is None
