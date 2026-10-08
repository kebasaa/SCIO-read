import base64
import importlib
import json

from scio_offline import research


class FakeResponse:
    def __init__(self, body, status=200):
        self.body, self.status_code = body, status

    def iter_content(self, size):
        yield self.body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _modules(monkeypatch):
    monkeypatch.syspath_prepend(str(research.DEV / 'scripts'))
    return importlib.import_module('firmware_recheck'), importlib.import_module('probe_foreign_firmware')


def _patch(monkeypatch, fw, bodies, calls, tmp_path):
    saved = {}
    monkeypatch.setattr(fw.r, 'write_new', lambda p, d: saved.update({p.name: d}))
    monkeypatch.setattr(fw.r, 'DEV', tmp_path)
    monkeypatch.setattr(fw.credentials, 'get_token', lambda **kw: 'unit-test-token')
    monkeypatch.setattr(fw.time, 'sleep', lambda s: None)

    def fake_get(url, params=None, headers=None, **kw):
        calls.append({'url': url, 'params': params})
        return FakeResponse(bodies[len(calls) - 1])
    monkeypatch.setattr(fw.requests, 'get', fake_get)
    return saved


def test_firmware_jobs_target_foreign_and_control(monkeypatch):
    _, probe = _modules(monkeypatch)
    foreign = {'0x57': '0x7C', '0x5A': '0x11', '0x5B': '0x0C', '0x5C': '0x8A',
               '0x64': '0x01', '0x65': '0x01', '0x66': '0x01', '0x67': '0x01'}
    jobs = probe.firmware_jobs(foreign, {'0x5C': '0x93'}, 'OWNBLE', '20150812-e:PRODUCTION')
    names = {j['name']: j for j in jobs}
    assert names['foreign_all_zero']['versions']['0x5C'] == '0x00'
    assert names['foreign_real_fw138']['versions']['0x5C'] == '0x8A'
    assert names['foreign_tables_outdated']['versions']['0x64'] == '0x00'
    assert names['foreign_tables_outdated']['versions']['0x5C'] == '0x8A'
    ctrl = names['own_device_control']
    assert ctrl['ble_id'] == 'OWNBLE' and ctrl['compression_version'] == '20150812-e:PRODUCTION'


def test_per_job_ble_id_override_hits_the_right_device(monkeypatch, tmp_path):
    fw, _ = _modules(monkeypatch)
    calls = []
    _patch(monkeypatch, fw, [b'{"new_version":null}'] * 2, calls, tmp_path)
    jobs = [{'name': 'foreign', 'versions': {}}, {'name': 'own', 'versions': {}, 'ble_id': 'OWNBLE'}]
    fw.run_firmware_jobs(tmp_path / 'run', jobs, True, 'FOREIGNBLE', 'tag')
    assert 'device/FOREIGNBLE/firmware-upgrade' in calls[0]['url']
    assert 'device/OWNBLE/firmware-upgrade' in calls[1]['url']


def test_describe_body_compares_both_header_tables(monkeypatch):
    fw, _ = _modules(monkeypatch)
    # body sized/checksummed to match the OWNER fw-147 dsp_op (32628 B, checksum 4151168)
    body = b'\xad' * 32628
    data = (4151168).to_bytes(4, 'little') + body
    foreign = {'dsp_op': (32212, 138, 4101455)}
    row = fw.describe_body('dsp_op', data, foreign)
    assert row['matches_unit_header_size'] and row['matches_unit_header_checksum']
    assert row['matches_foreign_header_size'] is False and row['matches_foreign_header_checksum'] is False


def test_offer_saved_to_gitignored_dir_and_halts(monkeypatch, tmp_path):
    fw, _ = _modules(monkeypatch)
    blob = (4101455).to_bytes(4, 'little') + b'\xad' * 32
    offer = json.dumps({'new_version': {'dsp_op': base64.b64encode(blob).decode()}}).encode()
    calls = []
    saved = _patch(monkeypatch, fw, [b'{"new_version":null}', offer, b'{"new_version":null}'], calls, tmp_path)
    jobs = [{'name': n, 'versions': {}} for n in ('a', 'b', 'c')]
    rows = fw.run_firmware_jobs(tmp_path / 'run', jobs, True, 'FBLE', 'tag',
                               saved_dir=tmp_path / 'fw', compare_headers={'dsp_op': (32212, 138, 4101455)})
    assert len(calls) == 2 and rows[1]['files'][0]['matches_foreign_header_checksum'] is True
    assert (tmp_path / 'fw' / 'dsp_op.bin').read_bytes() == blob[4:]
    assert 'unit-test-token' not in json.dumps(saved)


def test_replay_blocked_without_white_reference(monkeypatch):
    _, probe = _modules(monkeypatch)
    device = json.loads((research.DEV / 'analysis_output/foreign_fw138_20261008/device.json').read_text())
    jobs, note = probe.replay_jobs(device)
    assert len(jobs) == 1 and jobs[0]['name'] == 'control_scan'
    assert 'white reference' in note


def test_replay_builds_foreign_payload_when_white_present(monkeypatch):
    _, probe = _modules(monkeypatch)
    device = json.loads((research.DEV / 'analysis_output/foreign_fw138_20261008/device.json').read_text())
    b64 = device['blobs_b64']
    b64['sample_white'] = base64.b64encode(b'\x00' * 1800).decode()
    b64['sample_white_dark'] = base64.b64encode(b'\x01' * 1800).decode()
    jobs, note = probe.replay_jobs(device)
    assert len(jobs) == 2 and jobs[1]['name'] == 'foreign_fw138_scan'
    payload = jobs[1]['payload']
    assert payload['device_id'] == device['device']['device_id']
    assert payload['i2s_tag_config'] == '20150812:PRODUCTION'
    assert 'sample_white' in payload and 'sample' in payload
