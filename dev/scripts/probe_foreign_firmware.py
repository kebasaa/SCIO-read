"""Request firmware for a contributed older (fw-138) SCiO, then replay its scan.

A second owner contributed an older unit (fw DSP 138 / BLE 124, bare i2s tag
`20150812:PRODUCTION`, gradient 1416 B). Their device is out of date, so the
firmware-upgrade endpoint may offer the images the project has never obtained (the
owner's own fw-147 unit always gets `null`). Device specs are read from
`<run>/device.json` (contributor's personal details are not stored there).

Phase 1 - firmware (stop on the first offer): all-zero, the real fw-138 versions,
tables-outdated, and one control against the owner's own device to prove the token
and endpoint answer 200 null.

Phase 2 - scan replay (only if no firmware offered and nothing halted): the
contributed scan needs the contributor's white reference, which is not part of the
contribution. If white blobs are present in device.json the replay runs; otherwise it
is skipped with a note (no request is wasted).

Firmware bodies, if any, go to the git-ignored dev/recovered_firmware/<run>/ and are
never committed. Without --live only the plan is written.

    python dev/scripts/probe_foreign_firmware.py --output dev/analysis_output/foreign_fw138_20261008 [--live]
"""
import argparse
import base64
import json
import shutil
from pathlib import Path

import numpy as np

import _bootstrap  # noqa: F401
from scio import cloud, store
from scio_offline import research as r
from firmware_recheck import LIMITS, device_identity, run_firmware_jobs
from oracle_v2 import run_jobs

BUDGET = 10
OWN_SCAN = 'analysis_output/recovery_20261003/oracle_network/00'
WHITE_KEYS = ('sample_white', 'sample_white_dark')


def firmware_jobs(foreign_versions, own_versions, own_ble, own_tag):
    tables_outdated = {**foreign_versions, '0x64': '0x00', '0x65': '0x00', '0x66': '0x00', '0x67': '0x00'}
    return [
        {'name': 'foreign_all_zero', 'versions': {k: '0x00' for k in foreign_versions}},
        {'name': 'foreign_real_fw138', 'versions': foreign_versions},
        {'name': 'foreign_tables_outdated', 'versions': tables_outdated},
        {'name': 'own_device_control', 'versions': own_versions, 'ble_id': own_ble, 'compression_version': own_tag},
    ]


def replay_jobs(device):
    """Control scan (owner) + the contributed scan, or None if no white reference."""
    req = json.loads((r.DEV / (OWN_SCAN + '_request.json')).read_text())
    resp = json.loads((r.DEV / (OWN_SCAN + '_response.json')).read_text())
    if req['name'] != 'control_initial' or resp['status'] != 200 or len(resp['spectrum']) != 331:
        raise ValueError('unexpected stored control scan')
    jobs = [{'name': 'control_scan', 'payload': req['payload'], 'changes': {},
             'expected_spectrum': resp['spectrum']}]
    b64 = device.get('blobs_b64', {})
    if not all(k in b64 for k in WHITE_KEYS):
        return jobs, 'blocked: contributed scan has no white reference (need sample_white + sample_white_dark)'
    def blob(k):
        return base64.b64decode(b64[k])
    scan = {'blobs': {k: blob(k) for k in ('sample', 'sample_dark') if k in b64}
            | ({'sample_gradient': blob('sample_gradient')} if 'sample_gradient' in b64 else {}),
            'meta': {'sampled_at': device.get('sampled_at')}}
    white = {'blobs': {k: blob(k) for k in WHITE_KEYS}
             | ({'sample_white_gradient': blob('sample_white_gradient')} if 'sample_white_gradient' in b64 else {}),
             'meta': {'sampled_white_at': device.get('sampled_white_at')}}
    payload = cloud.build_scan_payload(scan, white, device['device']['device_id'],
                                       device['device']['i2s_tag_config'])
    jobs.append({'name': 'foreign_fw138_scan', 'payload': payload, 'changes': {},
                 'control_group': 'foreign'})
    return jobs, 'replay a contributed fw-138 scan under its own device_id + bare tag'


def mirror_to_bundle(out):
    """Copy all committed outputs into the gitignored contributor bundle."""
    bundle = r.DEV / 'private' / 'contrib_fw138'
    bundle.mkdir(parents=True, exist_ok=True)
    for src in sorted(out.glob('*.json')):
        shutil.copy2(src, bundle / src.name)
    private_run = r.DEV / 'private' / out.name           # raw server responses
    if private_run.exists():
        shutil.copytree(private_run, bundle / 'server_responses', dirs_exist_ok=True)
    saved = r.DEV / 'recovered_firmware' / out.name       # firmware bodies, if any
    if saved.exists():
        shutil.copytree(saved, bundle / 'firmware', dirs_exist_ok=True)


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--live', action='store_true')
    a = p.parse_args()
    out = a.output.resolve()
    if not out.is_relative_to(r.DEV):
        raise ValueError('output directory must be under dev')
    device = json.loads((out / 'device.json').read_text())
    foreign = device['device']
    own_identity, own_versions = device_identity()
    fw = firmware_jobs(device['current_versions'], own_versions,
                       own_identity['ble_id'].upper(), own_identity['i2s_tag_config'])
    replay, replay_note = replay_jobs(device)
    if len(fw) + len(replay) > BUDGET:
        raise ValueError('campaign exceeds request budget')
    r.write_new(out / 'predictions.json', {
        'firmware': 'Unknown. Prior probes returned null for the OWNER current device only; '
                    'this is the first genuinely old device (fw-138, bare 20150812 tag).',
        'replay': replay_note,
        'budget': BUDGET, 'planned_requests': len(fw) + len(replay)})

    saved = r.DEV / 'recovered_firmware' / out.name
    compare = {k: tuple(v) for k, v in device['file_headers'].items()}
    results = run_firmware_jobs(out, fw, a.live, foreign['ble_id'].upper(), foreign['i2s_tag_config'],
                               saved_dir=saved, budget=BUDGET, compare_headers=compare)
    offered = [f for row in results for f in row.get('files', [])]
    halted = (out / 'halt.json').exists() or any('halt_exception_type' in row for row in results)
    summary = {'contributed_device': {'firmware': foreign['firmware_version'],
                                       'i2s_tag_config': foreign['i2s_tag_config'],
                                       'ble_id': foreign['ble_id']},
               'firmware_results': results, 'offered_files': offered,
               'saved_dir': r.label(saved) if offered else None, 'firmware_limits': LIMITS,
               'replay_plan': replay_note}

    if not a.live:
        run_jobs(out, replay, False)
        return
    if offered:
        summary['replay'] = 'skipped: firmware offered'
    elif halted:
        summary['replay'] = 'skipped: firmware phase halted'
    elif len(replay) < 2:
        summary['replay'] = replay_note                      # blocked: no white reference
    else:
        run_jobs(out, replay, True)
        responses = {json.loads(x.read_text())['name']: json.loads(x.read_text())
                     for x in out.glob('*_response.json')}
        foreign_resp = responses.get('foreign_fw138_scan')
        if foreign_resp and foreign_resp.get('spectrum'):
            spec = foreign_resp['spectrum']
            (out / 'foreign_fw138_paired_sample.json').write_text(json.dumps({
                'schema': 'scio-foreign-pair/1', 'device_id': foreign['device_id'],
                'i2s_tag_config': foreign['i2s_tag_config'], 'firmware_version': foreign['firmware_version'],
                'blob_sha256': device['blob_sha256'],
                'spectrum': {'wavelength_nm': list(range(740, 1071)), 'reflectance': spec,
                             'n_points': len(spec)}}, indent=1), encoding='utf-8')
            summary['replay'] = {'status': foreign_resp['status'], 'spectrum_points': len(spec)}
        else:
            summary['replay'] = {'status': foreign_resp['status'] if foreign_resp else None,
                                 'response': foreign_resp['response'] if foreign_resp else None}
    r.write_new(out / 'campaign_summary.json', summary)
    mirror_to_bundle(out)
    print(json.dumps({'offered_files': summary['offered_files'], 'replay': summary['replay']}))


if __name__ == '__main__':
    main()
