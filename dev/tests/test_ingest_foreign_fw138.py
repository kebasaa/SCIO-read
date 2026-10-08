import base64
import importlib
import json

from scio import session, store
from scio_offline import leakage as L
from scio_offline import research


def _tiny_run(tmp_path):
    """A minimal device.json + scans.json (white + one sample), synthetic blobs."""
    run = tmp_path / "run"
    run.mkdir()
    def b(seed, n):
        return base64.b64encode(bytes([seed] * n)).decode()
    (run / "device.json").write_text(json.dumps({"device": {
        "device_id": "E02E60F46B7CD55F", "serial": "X", "firmware_version": 138}}))
    temp = {"raw_u32": [405, 2665, 3263], "cmos_t": 21.1, "cmos_t_app": 21,
            "chip_t": 26.65, "obj_t": 32.63}
    (run / "scans.json").write_text(json.dumps({
        "device_id": "E02E60F46B7CD55F", "i2s_tag_config": "20150812:PRODUCTION",
        "firmware_version": 138,
        "white_reference": {"temperature": temp, "blobs_b64": {
            "sample_white": b(10, 1800), "sample_white_dark": b(11, 1800),
            "sample_white_gradient": b(12, 1416)}},
        "samples": [{"material": "skin", "temperature": temp, "blobs_b64": {
            "sample": b(1, 1800), "sample_dark": b(2, 1800), "sample_gradient": b(3, 1416)}}]}))
    return run


def test_ingest_builds_valid_canonical_fw138_record(tmp_path):
    ingest = importlib.import_module("ingest_foreign_fw138") if False else None  # noqa: F841
    import sys
    sys.path.insert(0, str(research.DEV / "scripts"))
    mod = importlib.import_module("ingest_foreign_fw138")
    run = _tiny_run(tmp_path)
    wr_path, written = mod.build_records(run_dir=run, wr_dir=tmp_path / "wr", scans_dir=tmp_path / "scans")
    assert len(written) == 1
    rec = session.load_record(written[0])
    assert rec["schema"] == "scio-scan/2"
    assert rec["device"]["device_id"] == "E02E60F46B7CD55F"
    assert rec["device"]["i2s_tag_config"] == "20150812:PRODUCTION"
    assert rec["temperature"]["scan_before"]["obj_t"] == 32.63
    scan_b, white_b = session.record_blobs(rec)
    assert len(scan_b["sample_gradient"]) == 1416 and len(white_b["sample_white"]) == 1800
    payload = session.to_payload(rec)          # server-ready, his identity
    assert payload["device_id"] == "E02E60F46B7CD55F" and payload["i2s_tag_config"] == "20150812:PRODUCTION"
    assert store.WR_DIR.exists()               # real dirs untouched beyond existence


def test_corpus_groups_separate_devices_and_load_selects_one():
    rows = []
    for dev, n in (("OWNER", 5), ("FOREIGN", 2)):
        for i in range(n):
            rows.append({"blobs": {"sample": bytes([i + 1]) * 1800, "sample_dark": bytes([i + 2]) * 1800},
                         "device": {"device_id": dev}, "acquisition_group": "g", "white_group": "w",
                         "truth": {"reflectance": [0.5] * 3, "wavelength_nm": [740, 741, 742]}})
    groups = L.corpus_groups(rows, frozen=set())
    assert {k: len(v) for k, v in groups.items()} == {"OWNER": 5, "FOREIGN": 2}
    assert L.load_corpus(rows, frozen=set())["device_id"] == "OWNER"       # default = largest
    foreign = L.load_corpus(rows, frozen=set(), device_id="FOREIGN")
    assert foreign["device_id"] == "FOREIGN" and foreign["n"] == 2
