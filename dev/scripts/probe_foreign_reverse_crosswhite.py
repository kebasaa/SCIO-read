"""Reverse cross-white: does the OWNER's sample decode with the CONTRIBUTOR's white?

The forward test (`probe_foreign_crosswhite.py`) grafted the fw-138 sample+dark onto
the owner's valid scan (owner white kept) and the server rejected both identities with
`400 Bad_sample_signature`. This is the untested mirror: keep the owner's sample+dark
(and owner sample gradient), but replace the WHITE reference's two non-gradient blobs
(`sample_white`, `sample_white_dark`) with the contributor fw-138 white reference, and
submit two ways - under the owner's device_id + `-e` tag, and under the contributor's
device_id + bare tag.

Design mirrors the forward probe for a clean comparison: only the two non-gradient
blobs of the swapped role are replaced; the gradient is kept (here the owner's
`sample_white_gradient`), exactly as the forward test kept the owner's
`sample_gradient`.

Expectation (same logic as forward): both rejected `400 Bad_sample_signature` - one
side's blobs never match the request's device_id. A `200` + spectrum would be a major
result: it would mean the sample side and the white side validate independently, i.e.
a white reference from device A works with sample data from device B.

A known owner scan is sent first and last as controls. At most 4 requests, 20 s apart.
Live requests require --live.

    python dev/scripts/probe_foreign_reverse_crosswhite.py --output dev/analysis_output/<new-run> [--live]
"""
import argparse
import base64
import json
from pathlib import Path

import _bootstrap  # noqa: F401
from scio import store
from scio_offline import research as r
from oracle_v2 import run_jobs

OWN_SCAN = 'analysis_output/recovery_20261003/oracle_network/00'
FW138_SCANS = 'analysis_output/foreign_fw138_retake_20261008/scans.json'


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--live', action='store_true')
    a = p.parse_args()
    out = a.output.resolve()
    if not out.is_relative_to(r.DEV) or out.exists():
        raise ValueError('new output directory under dev required')

    req = json.loads((r.DEV / (OWN_SCAN + '_request.json')).read_text())
    resp = json.loads((r.DEV / (OWN_SCAN + '_response.json')).read_text())
    if req['name'] != 'control_initial' or resp['status'] != 200:
        raise ValueError('unexpected stored control scan')
    base = req['payload']                                   # owner's full, valid scan

    fw = json.loads((r.DEV / FW138_SCANS).read_text())
    wb = fw['white_reference']['blobs_b64']                 # fw-138 white reference
    foreign_id = fw['device_id']
    foreign_tag = fw['i2s_tag_config']

    def cross(device_id, tag):
        pay = dict(base)                                    # keep owner's sample + gradients
        pay['sample_white'] = store.wrap_b64(base64.b64decode(wb['sample_white']))
        pay['sample_white_dark'] = store.wrap_b64(base64.b64decode(wb['sample_white_dark']))
        pay['device_id'] = device_id
        pay['i2s_tag_config'] = tag
        return pay

    owner_id, owner_tag = base['device_id'], base['i2s_tag_config']
    jobs = [
        {'name': 'control_initial', 'payload': base, 'changes': {}, 'expected_spectrum': resp['spectrum']},
        {'name': 'cross_owner_identity',
         'payload': cross(owner_id, owner_tag), 'control_group': 'cross',
         'changes': {'sample_white': {'op': 'foreign fw-138 white'},
                     'sample_white_dark': {'op': 'foreign fw-138 white dark'}}},
        {'name': 'cross_foreign_identity',
         'payload': cross(foreign_id, foreign_tag), 'control_group': 'cross',
         'changes': {'sample_white': {'op': 'foreign fw-138 white'},
                     'sample_white_dark': {'op': 'foreign fw-138 white dark'},
                     'device_id': {'op': 'foreign'}, 'i2s_tag_config': {'op': 'foreign bare tag'}}},
        {'name': 'control_final', 'payload': base, 'changes': {}, 'expected_spectrum': resp['spectrum']},
    ]
    r.write_new(out / 'predictions.json', {
        'hypothesis': 'Reverse direction (owner sample + fw-138 white). Both cross combinations are '
                      'expected rejected (device-bound per-blob signature). A 200 + spectrum would '
                      'mean a white reference from device A works with sample data from device B.',
        'planned_requests': len(jobs)})
    run_jobs(out, jobs, a.live)
    if not a.live or (out / 'halt.json').exists():
        return
    responses = {json.loads(x.read_text())['name']: json.loads(x.read_text()) for x in out.glob('*_response.json')}
    summary = {name: {'status': responses[name]['status'],
                      'decoded': bool(responses[name].get('spectrum')),
                      'error_type': (responses[name].get('response') or {}).get('error_type')}
               for name in ('cross_owner_identity', 'cross_foreign_identity') if name in responses}
    r.write_new(out / 'reverse_crosswhite_summary.json', {
        'results': summary,
        'direction': 'owner sample + fw-138 white reference (mirror of probe_foreign_crosswhite.py)',
        'limits': 'Rejection confirms the request device_id must match every non-gradient blob; '
                  'it does not reveal the signature algorithm, the payload transform, or isolate '
                  'which blob failed. The white gradient was kept (owner), mirroring the forward test.'})
    print(json.dumps(summary))


if __name__ == '__main__':
    main()
