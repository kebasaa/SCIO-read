"""Which field does the server use to bind a blob to a device? (single-variable)

Both cross-white directions reject with `400 Bad_sample_signature`, flagging whichever
side is "wrong" for the request identity. This isolates WHAT the server reads to decide
a side is wrong - the request `device_id`, the `i2s_tag_config`, or an id embedded in
the blob. That field is the most likely input to the per-device key.

Design: start from the owner's fully valid scan (decodes 200) and change ONE request
identity field at a time, keeping all owner blobs:
  * owner_blobs__id_fw138   - only request device_id -> fw-138 (tag stays owner)
  * owner_blobs__tag_fw138  - only request i2s_tag   -> fw-138 bare (id stays owner)
  * owner_blobs__id_tag_fw138 - both request fields -> fw-138

Interpretation on the owner-blob jobs:
  * rejects (Bad_sample_signature) -> that request field is used to validate/key the blobs.
  * still 200 -> the server ignores that request field and reads an id embedded in the
    blob header; the binding field is inside the blob, not the request metadata.

Two mixed-identity cross-checks (owner sample + fw-138 white, one identity field flipped)
show which side the flag follows:
  * fw138white__id_fw138_tag_owner
  * fw138white__id_owner_tag_fw138

Controls (unchanged owner scan) first, middle and last. At most 8 requests, 20 s apart.
Live requires --live.

    python dev/scripts/probe_signature_field_isolation.py --output dev/analysis_output/<new-run> [--live]
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
    owner_id, owner_tag = base['device_id'], base['i2s_tag_config']

    fw = json.loads((r.DEV / FW138_SCANS).read_text())
    wb = fw['white_reference']['blobs_b64']                 # fw-138 white reference
    foreign_id, foreign_tag = fw['device_id'], fw['i2s_tag_config']

    def ident(device_id, tag, foreign_white=False):
        pay = dict(base)
        if foreign_white:
            pay['sample_white'] = store.wrap_b64(base64.b64decode(wb['sample_white']))
            pay['sample_white_dark'] = store.wrap_b64(base64.b64decode(wb['sample_white_dark']))
        pay['device_id'] = device_id
        pay['i2s_tag_config'] = tag
        return pay

    ctrl = {'name': 'control', 'payload': base, 'changes': {}, 'expected_spectrum': resp['spectrum']}
    jobs = [
        dict(ctrl, name='control_initial'),
        {'name': 'owner_blobs__id_fw138',
         'payload': ident(foreign_id, owner_tag), 'control_group': 'idfield',
         'changes': {'device_id': {'op': 'foreign (tag + all blobs stay owner)'}}},
        {'name': 'owner_blobs__tag_fw138',
         'payload': ident(owner_id, foreign_tag), 'control_group': 'idfield',
         'changes': {'i2s_tag_config': {'op': 'foreign bare (device_id + all blobs stay owner)'}}},
        {'name': 'owner_blobs__id_tag_fw138',
         'payload': ident(foreign_id, foreign_tag), 'control_group': 'idfield',
         'changes': {'device_id': {'op': 'foreign'}, 'i2s_tag_config': {'op': 'foreign bare'}}},
        dict(ctrl, name='control_mid'),
        {'name': 'fw138white__id_fw138_tag_owner',
         'payload': ident(foreign_id, owner_tag, foreign_white=True), 'control_group': 'mixed',
         'changes': {'sample_white': {'op': 'foreign fw-138'}, 'sample_white_dark': {'op': 'foreign fw-138'},
                     'device_id': {'op': 'foreign'}}},
        {'name': 'fw138white__id_owner_tag_fw138',
         'payload': ident(owner_id, foreign_tag, foreign_white=True), 'control_group': 'mixed',
         'changes': {'sample_white': {'op': 'foreign fw-138'}, 'sample_white_dark': {'op': 'foreign fw-138'},
                     'i2s_tag_config': {'op': 'foreign bare'}}},
        dict(ctrl, name='control_final'),
    ]
    r.write_new(out / 'predictions.json', {
        'hypothesis': 'On owner-blob jobs, a 400 Bad_sample_signature means that changed request '
                      'field is used to validate/key the blobs; a 200 means the server reads an id '
                      'embedded in the blob instead. device_id is the leading candidate for the key.',
        'planned_requests': len(jobs)})
    run_jobs(out, jobs, a.live)
    if not a.live or (out / 'halt.json').exists():
        return
    responses = {json.loads(x.read_text())['name']: json.loads(x.read_text()) for x in out.glob('*_response.json')}
    names = ('owner_blobs__id_fw138', 'owner_blobs__tag_fw138', 'owner_blobs__id_tag_fw138',
             'fw138white__id_fw138_tag_owner', 'fw138white__id_owner_tag_fw138')
    summary = {n: {'status': responses[n]['status'],
                   'decoded': bool(responses[n].get('spectrum')),
                   'error_type': (responses[n].get('response') or {}).get('error_type'),
                   'flagged_side': (responses[n].get('response') or {}).get('spectrum')}
               for n in names if n in responses}
    r.write_new(out / 'field_isolation_summary.json', {
        'results': summary,
        'reading': 'owner_blobs__* that reject -> that request field validates/keys the blobs; '
                   'if they decode 200 -> binding id is embedded in the blob header, not the request.',
        'limits': 'Identifies which request field gates validation; it does not reveal the signature '
                  'algorithm or prove that field is literally the decryption key.'})
    print(json.dumps(summary, indent=1))


if __name__ == '__main__':
    main()
