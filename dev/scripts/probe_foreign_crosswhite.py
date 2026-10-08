"""Does a contributed foreign scan decode when paired with the owner's white reference?

The contributed fw-138 scan has no white reference, so it cannot be replayed on its
own. This test instead pairs the contributor's sample+dark with the OWNER's white
reference and submits it two ways: under the owner's device_id + `-e` tag, and under
the contributor's device_id + bare tag. The per-blob signature is device-bound, so
both are expected to be rejected (`400 Bad_sample_signature`) - one side's blobs never
match the request's device_id. A `200` with a spectrum would be a major result
(sample side and white side validated independently). Either way it is informative.

A known owner scan is sent first as the control. At most 4 requests, 20 s apart.

    python dev/scripts/probe_foreign_crosswhite.py --output dev/analysis_output/<new-run> [--live]
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
DEVICE = 'analysis_output/foreign_fw138_20261008/device.json'


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
    device = json.loads((r.DEV / DEVICE).read_text())
    b64 = device['blobs_b64']
    base = req['payload']                                   # owner's full, valid scan

    def cross(device_id, tag):
        pay = dict(base)                                    # keep owner's white + gradients
        pay['sample'] = store.wrap_b64(base64.b64decode(b64['sample']))
        pay['sample_dark'] = store.wrap_b64(base64.b64decode(b64['sample_dark']))
        pay['device_id'] = device_id
        pay['i2s_tag_config'] = tag
        return pay

    owner_id, owner_tag = base['device_id'], base['i2s_tag_config']
    foreign = device['device']
    jobs = [
        {'name': 'control_initial', 'payload': base, 'changes': {}, 'expected_spectrum': resp['spectrum']},
        {'name': 'cross_owner_identity',
         'payload': cross(owner_id, owner_tag), 'control_group': 'cross',
         'changes': {'sample': {'op': 'foreign fw-138 sample'}, 'sample_dark': {'op': 'foreign fw-138 dark'}}},
        {'name': 'cross_foreign_identity',
         'payload': cross(foreign['device_id'], foreign['i2s_tag_config']), 'control_group': 'cross',
         'changes': {'device_id': {'op': 'foreign'}, 'i2s_tag_config': {'op': 'foreign bare tag'}}},
        {'name': 'control_final', 'payload': base, 'changes': {}, 'expected_spectrum': resp['spectrum']},
    ]
    r.write_new(out / 'predictions.json', {
        'hypothesis': 'Both cross combinations are rejected (device-bound per-blob signature). '
                      'A 200 + spectrum would mean sample and white sides validate independently.',
        'planned_requests': len(jobs)})
    run_jobs(out, jobs, a.live)
    if not a.live or (out / 'halt.json').exists():
        return
    responses = {json.loads(x.read_text())['name']: json.loads(x.read_text()) for x in out.glob('*_response.json')}
    summary = {name: {'status': responses[name]['status'],
                      'decoded': bool(responses[name].get('spectrum')),
                      'error_type': (responses[name].get('response') or {}).get('error_type')}
               for name in ('cross_owner_identity', 'cross_foreign_identity') if name in responses}
    r.write_new(out / 'crosswhite_summary.json', {
        'results': summary,
        'limits': 'Rejection confirms the request device_id must match every non-gradient blob; '
                  'it does not reveal the signature algorithm or the payload transform.'})
    print(json.dumps(summary))


if __name__ == '__main__':
    main()
