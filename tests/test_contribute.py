"""Device identity travels with every scan, and contributor bundles round-trip.

No hardware, no network: a ScioDevice with canned responses, and the
session-level fake from ``test_pipeline``.
"""

import json
import zipfile

import pytest

from scio import contribute, protocol, session
from scio.device import ScioDevice
from scio.protocol import Cmd, ScioTimeout

from test_pipeline import _FakeScio

I2S = b"20150812:PRODUCTION"


class _CannedDevice(ScioDevice):
    """Real ScioDevice queries over canned frames; counts what was sent."""
    SLEEP_BETWEEN_COMMANDS = 0

    def __init__(self, ble_ok=True):
        super().__init__()
        self.sent = []
        self.ble_ok = ble_ok

    def _command(self, cmd, payload=b"", allow_write=False):
        self.sent.append(cmd)
        if cmd == Cmd.READ_DEVICE_ID:
            return protocol.Response(cmd, 26, bytes(range(1, 27)))
        if cmd == Cmd.READ_BLE_ID:
            if not self.ble_ok:
                raise ScioTimeout("no reply")
            data = bytearray(130)
            data[66:66 + len(I2S)] = I2S
            return protocol.Response(cmd, 130, bytes(data))
        if cmd == Cmd.READ_TEMPERATURE:
            return protocol.Response(cmd, 12, bytes(12))
        raise AssertionError(f"unexpected command 0x{cmd:02X}")

    def raw_command(self, cmd, payload=b"", n_responses=1, allow_write=False):
        self.sent.append(cmd)
        sizes = (1800, 1800, 1416)[:n_responses]
        return [protocol.Response(cmd, n, bytes(n)) for n in sizes]


def test_sample_spectrum_carries_identity_and_temperatures():
    dev = _CannedDevice()
    scan = dev.sample_spectrum(151)
    assert scan["device"]["device_id"] and scan["device"]["i2s_tag_config"] == I2S.decode()
    assert set(scan["temperature"]) == {"before", "after"}
    dev.sample_spectrum(151)
    # identity is read once per connection, not before every scan
    assert dev.sent.count(Cmd.READ_DEVICE_ID) == 1


def test_white_reference_carries_identity_and_still_saves(tmp_path):
    from scio import store
    dev = _CannedDevice()
    wr = dev.white_reference(151)
    assert wr["device"]["device_id"]
    path = store.save_calibration(wr, wr["device"], {}, {}, out_dir=tmp_path)
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert set(saved["sizes"]) == {"sample_white", "sample_white_dark", "sample_white_gradient"}


def test_identity_flags_a_missing_i2s_tag():
    dev = _CannedDevice(ble_ok=False)
    assert dev.sample_spectrum(151)["device"]["i2s_tag_missing"] is True


class _NoTag(_FakeScio):
    def read_device_info(self):
        return {"device_id": "FAKEDEV0000CAFE", "i2s_tag_config": "", "firmware_version": 151}


def test_capture_refuses_a_device_without_its_tag(tmp_path):
    kw = dict(out_dir=tmp_path / "scans", wr_dir=tmp_path / "wr",
              thresholds=dict(session.THRESHOLDS_FALLBACK), on_calibration_needed=lambda r: True)
    with pytest.raises(RuntimeError, match="i2s_tag_config"):
        session.capture(_NoTag(), "x", **kw)
    assert not (tmp_path / "scans").exists()
    assert session.capture(_NoTag(), "x", allow_incomplete=True, **kw).exists()


def _bundle(tmp_path, count=3):
    prompts = []
    zip_path = contribute.capture_bundle(_FakeScio(), "closed cap", count, tmp_path / "out",
                                         on_calibration_needed=lambda r: prompts.append(r) or True)
    return zip_path, prompts


def test_bundle_has_identity_white_and_scans(tmp_path):
    zip_path, prompts = _bundle(tmp_path)
    assert len(prompts) == 1                     # one white reference, taken first
    b = contribute.read_bundle(zip_path)
    assert b["manifest"]["device"]["device_id"] == "FAKEDEV0000CAFE"
    assert len(b["whites"]) == 1 and len(b["scans"]) == 3
    assert b["manifest"]["location"] == "not recorded"
    assert all(rec["mobile_GPS"] == session.location.empty_gps() for _, rec in b["scans"])


def test_import_copies_once_and_points_at_the_imported_white(tmp_path):
    zip_path, _ = _bundle(tmp_path)
    scans, wr = tmp_path / "scans", tmp_path / "wr"
    first = contribute.import_bundle(zip_path, scans_dir=scans, wr_dir=wr)
    assert len(first["imported"]) == 3 and len(first["white_references"]) == 1
    rec = session.load_record(next(scans.glob("*.json")))
    assert rec["provenance"]["source"].startswith("contributor bundle ")
    assert rec["white_reference"]["source"] == first["white_references"][0]
    session.to_payload(rec)                       # the server would accept its shape
    again = contribute.import_bundle(zip_path, scans_dir=scans, wr_dir=wr)
    assert again["imported"] == [] and len(again["skipped"]) == 3 and again["white_references"] == []
    assert len(list(scans.glob("*.json"))) == 3 and len(list(wr.glob("*.json"))) == 1


def _rewrite(zip_path, out, edit):
    with zipfile.ZipFile(zip_path) as zf:
        files = {n: zf.read(n) for n in zf.namelist()}
    edit(files)
    with zipfile.ZipFile(out, "w") as zf:
        for n, d in files.items():
            zf.writestr(n, d)
    return out


def test_import_refuses_a_tampered_record(tmp_path):
    zip_path, _ = _bundle(tmp_path, count=1)

    def tamper(files):
        name = next(n for n in files if n.startswith("scans/") and n.endswith(".json"))
        files[name] = files[name].replace(b"closed cap", b"closed cup")

    bad = _rewrite(zip_path, tmp_path / "bad.zip", tamper)
    with pytest.raises(ValueError, match="hash mismatch"):
        contribute.import_bundle(bad, scans_dir=tmp_path / "s", wr_dir=tmp_path / "w")
    assert not (tmp_path / "s").exists()


def test_import_refuses_a_white_from_another_device(tmp_path):
    zip_path, _ = _bundle(tmp_path, count=1)

    def swap(files):
        name = next(n for n in files if n.startswith("white/") and n.endswith(".json"))
        wr = json.loads(files[name])
        wr["device"]["device_id"] = "0000000000000000"
        files[name] = json.dumps(wr).encode()
        man = json.loads(files["manifest.json"])
        for e in man["white_references"]:
            e["sha256"] = contribute._sha256(files[name])
        files["manifest.json"] = json.dumps(man).encode()

    bad = _rewrite(zip_path, tmp_path / "bad.zip", swap)
    with pytest.raises(ValueError, match="another device"):
        contribute.read_bundle(bad)


def test_import_refuses_paths_outside_the_bundle_layout(tmp_path):
    zip_path, _ = _bundle(tmp_path, count=1)

    def escape(files):
        man = json.loads(files["manifest.json"])
        man["scans"][0]["file"] = "../evil.json"
        files["manifest.json"] = json.dumps(man).encode()
        files["../evil.json"] = b"{}"

    bad = _rewrite(zip_path, tmp_path / "bad.zip", escape)
    with pytest.raises(ValueError, match="unexpected bundle member"):
        contribute.read_bundle(bad)
