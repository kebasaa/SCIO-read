import base64
import importlib
import json
from types import SimpleNamespace

import numpy as np
from scio_offline import research


def _modules(monkeypatch):
    monkeypatch.syspath_prepend(str(research.DEV / 'scripts'))
    return importlib.import_module('firmware_recheck'), importlib.import_module('probe_old_firmware')


class FakeResponse:
    def __init__(self, body, status=200):
        self.body, self.status_code = body, status

    def iter_content(self, size):
        yield self.body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _patch_transport(monkeypatch, fw, bodies, calls, tmp_path):
    saved = {}

    def write_new(path, data):
        saved[path.name] = data
    monkeypatch.setattr(fw.r, 'write_new', write_new)
    monkeypatch.setattr(fw.r, 'DEV', tmp_path)
    monkeypatch.setattr(fw.credentials, 'get_token', lambda **kw: 'unit-test-token')
    monkeypatch.setattr(fw.time, 'sleep', lambda s: None)

    def fake_get(url, params=None, headers=None, **kw):
        calls.append({'url': url, 'params': params, 'headers': headers})
        return FakeResponse(bodies[len(calls) - 1])
    monkeypatch.setattr(fw.requests, 'get', fake_get)
    return saved


def test_budget_and_job_shape(monkeypatch):
    fw, probe = _modules(monkeypatch)
    _, current = fw.device_identity()
    jobs = probe.firmware_jobs(current)
    assert len(jobs) + 2 <= probe.BUDGET
    names = {j['name']: j for j in jobs}
    assert names['dsp_op_136']['versions']['0x5C'] == '0x88'
    assert names['dsp_op_135']['versions']['0x5C'] == '0x87'
    assert names['old_device_135_old_app']['client'] == probe.OLD_CLIENT


def test_dry_run_sends_nothing(monkeypatch, tmp_path):
    fw, _ = _modules(monkeypatch)
    calls = []
    saved = _patch_transport(monkeypatch, fw, [], calls, tmp_path)
    fw.run_firmware_jobs(tmp_path / 'run', [{'name': 'a', 'versions': {}}], False, 'ID', 'tag')
    assert calls == [] and 'firmware_plan.json' in saved


def test_null_continues_and_offer_halts_and_is_saved(monkeypatch, tmp_path):
    fw, _ = _modules(monkeypatch)
    blob = (4151168).to_bytes(4, 'little') + b'\xad' * 40
    offer = json.dumps({'new_version': {'dsp_op': base64.b64encode(blob).decode()}}).encode()
    null = b'{"new_version":null}'
    calls = []
    saved = _patch_transport(monkeypatch, fw, [null, offer, null], calls, tmp_path)
    jobs = [{'name': n, 'versions': {'0x5C': '0x87'}} for n in ('a', 'b', 'c')]
    rows = fw.run_firmware_jobs(tmp_path / 'run', jobs, True, 'ID', 'tag', saved_dir=tmp_path / 'fw')
    assert len(calls) == 2 and len(rows) == 2
    assert rows[1]['files'][0]['matches_unit_header_checksum'] is True
    assert (tmp_path / 'fw' / 'dsp_op.bin').read_bytes() == blob[4:]
    assert 'unit-test-token' not in json.dumps(saved)


def test_client_header_per_job(monkeypatch, tmp_path):
    fw, _ = _modules(monkeypatch)
    calls = []
    _patch_transport(monkeypatch, fw, [b'{"new_version":null}'] * 2, calls, tmp_path)
    fw.run_firmware_jobs(tmp_path / 'run', [{'name': 'a', 'versions': {}},
                                            {'name': 'b', 'versions': {}, 'client': 'Android 1.2.6.476'}],
                         True, 'ID', 'tag')
    assert [c['headers']['X-SCiO-Client-Version'] for c in calls] == ['Android 1.3.8.554', 'Android 1.2.6.476']


def test_scan_runner_client_version(monkeypatch):
    monkeypatch.syspath_prepend(str(research.DEV / 'scripts'))
    oracle = importlib.import_module('oracle_v2')
    monkeypatch.setattr(oracle.r, 'write_new', lambda p, d: None)
    monkeypatch.setattr(oracle.credentials, 'get_token', lambda **kw: 'unit-test-token')
    monkeypatch.setattr(oracle.time, 'sleep', lambda s: None)
    monkeypatch.setattr(oracle.cloud, 'spectrum_from_response', lambda resp: (np.arange(740, 1071), np.ones(331)))
    headers = []

    def fake_post(*a, **kw):
        headers.append(kw['headers']['X-SCiO-Client-Version'])
        return SimpleNamespace(status_code=200, json=lambda: {})
    monkeypatch.setattr(oracle.requests, 'post', fake_post)
    oracle.run_jobs(research.DEV / 'unused-test-output', [
        {'name': 'control_scan', 'payload': {}, 'changes': {}},
        {'name': 'old', 'payload': {}, 'changes': {}, 'client_version': 'Android 1.2.6.476'}], live=True)
    assert headers == ['Android 1.3.8.554', 'Android 1.2.6.476']


def test_old_format_scan_drops_only_gradients(monkeypatch):
    _, probe = _modules(monkeypatch)
    control, old = probe.scan_jobs()
    assert set(control['payload']) - set(old['payload']) == set(probe.GRADIENTS)
    assert all(old['payload'][k] == control['payload'][k] for k in old['payload'])
