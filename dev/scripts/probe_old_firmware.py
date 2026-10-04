"""Ask for firmware as a firmware-135/136 device, then send one old-format scan.

Phase 1 sends six firmware-upgrade GETs (controls, dsp_op 136/135, an all-files-old
device, and the same with the 1.2.6.476 app client string). Phase 2 runs only if no
firmware was offered and nothing halted: an intact historical scan as control, then the
same scan without gradients (as firmware < 136 sends it) under the old client string.
At most 10 requests in total, at least 20 s apart. Without --live only plans are written.

    python dev/scripts/probe_old_firmware.py --output dev/analysis_output/<new-run> [--live]
"""
import argparse
import json
from pathlib import Path
import numpy as np
import _bootstrap
from scio_offline import research as r
from firmware_recheck import DEFAULT_CLIENT, LIMITS, device_identity, run_firmware_jobs
from oracle_v2 import run_jobs

BUDGET = 10
OLD_CLIENT = 'Android 1.2.6.476'
SCAN_SOURCE = 'analysis_output/recovery_20261003/oracle_network/00'
GRADIENTS = ('sample_gradient', 'sample_white_gradient')


def firmware_jobs(current):
    old = {'0x57': '0x7C', '0x5A': '0x10', '0x5B': '0x0B', '0x5C': '0x87'}
    return [
        {'name': 'control_current', 'versions': current},
        {'name': 'dsp_op_136', 'versions': {**current, '0x5C': '0x88'}},
        {'name': 'dsp_op_135', 'versions': {**current, '0x5C': '0x87'}},
        {'name': 'old_device_135', 'versions': old},
        {'name': 'old_device_135_old_app', 'versions': old, 'client': OLD_CLIENT},
        {'name': 'control_current_final', 'versions': current},
    ]


def scan_jobs():
    request = json.loads((r.DEV / (SCAN_SOURCE + '_request.json')).read_text())
    response = json.loads((r.DEV / (SCAN_SOURCE + '_response.json')).read_text())
    if request['name'] != 'control_initial' or response['status'] != 200 or len(response['spectrum']) != 331:
        raise ValueError('unexpected stored control')
    base = request['payload']
    old = {k: v for k, v in base.items() if k not in GRADIENTS}
    return [
        {'name': 'control_scan', 'payload': base, 'changes': {}, 'expected_spectrum': response['spectrum']},
        {'name': 'old_format_no_gradients', 'payload': old, 'client_version': OLD_CLIENT,
         'changes': {g: {'operation': 'omit'} for g in GRADIENTS}},
    ]


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--live', action='store_true')
    a = p.parse_args()
    out = a.output.resolve()
    if not out.is_relative_to(r.DEV) or out.exists():
        raise ValueError('new output directory under dev required')
    identity, current = device_identity()
    fw, scans = firmware_jobs(current), scan_jobs()
    if len(fw) + len(scans) > BUDGET:
        raise ValueError('campaign exceeds request budget')
    r.write_new(out / 'predictions.json', {
        'firmware': 'new_version null for every job (all lower versions down to 0 were null in 2026-09)',
        'old_format_scan': 'spectrum identical to control_scan on all 331 bands, atol=rtol=1e-6',
        'budget': BUDGET, 'planned_requests': len(fw) + len(scans),
        'default_client': DEFAULT_CLIENT, 'old_client': OLD_CLIENT})
    saved = r.DEV / 'recovered_firmware' / out.name
    results = run_firmware_jobs(out, fw, a.live, identity['ble_id'].upper(), identity['i2s_tag_config'],
                                saved_dir=saved, budget=BUDGET)
    offered = [f for row in results for f in row.get('files', [])]
    halted = (out / 'halt.json').exists() or any('halt_exception_type' in row for row in results)
    summary = {'firmware_results': results, 'offered_files': offered,
               'saved_dir': r.label(saved) if offered else None, 'firmware_limits': LIMITS}
    if not a.live:
        run_jobs(out, scans, False)
        return
    if offered or halted:
        summary['scan_phase'] = 'skipped: firmware offered' if offered else 'skipped: firmware phase halted'
        r.write_new(out / 'campaign_summary.json', summary)
        print(summary['scan_phase'])
        return
    run_jobs(out, scans, True)
    responses = {json.loads(x.read_text())['name']: json.loads(x.read_text()) for x in out.glob('*_response.json')}
    control, old = responses.get('control_scan'), responses.get('old_format_no_gradients')
    if control and old and control['spectrum'] and old['spectrum']:
        delta = np.abs(np.asarray(old['spectrum']) - np.asarray(control['spectrum']))
        summary['old_format_scan'] = {'status': old['status'], 'equivalent': bool(np.allclose(
            old['spectrum'], control['spectrum'], atol=1e-6, rtol=1e-6)), 'max_absolute_error': float(delta.max())}
    else:
        summary['old_format_scan'] = {'status': old['status'] if old else None, 'equivalent': None,
                                      'response': old['response'] if old else None}
    r.write_new(out / 'campaign_summary.json', summary)
    print(json.dumps({k: summary[k] for k in ('offered_files', 'old_format_scan')}))


if __name__ == '__main__':
    main()
