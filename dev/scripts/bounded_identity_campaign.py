"""Plan, self-test or run a network-disabled, dev-only recovery campaign."""
import argparse
import json
import socket
import sqlite3
import subprocess
import sys
from pathlib import Path
import _bootstrap
from scio_offline import bounded_campaign as c, research as r
from identifier_key_gap_search import KNOWN_IDENTITY


def deny(*args, **kwargs):
    raise RuntimeError('network disabled for offline campaign')


def prepare():
    aes_path = Path('dev/analysis_output/recovery_20261003/key_search_confirmed.json')
    gap_path = Path('dev/analysis_output/identifier_key_gap_20261004/identifier_key_gap.json')
    aes = json.loads(aes_path.read_text())['groups'][0]
    gap = json.loads(gap_path.read_text())
    # Only canonical historical acquisitions; frozen fresh_reference files are never loaded.
    rows = [x for x in r.contexts() if x['device'].get('device_id') == aes['device_id']]
    rows = [x for x in rows if x['acquisition_group'] < '2026-10-03']
    rows.sort(key=lambda x: (x['acquisition_group'], x['id']))
    if not rows:
        raise ValueError('no historical exploratory records')
    first = rows[0]
    device = c.bind_identity(first['device'], KNOWN_IDENTITY, '8032AB45611198F1')
    # This explicit identity injection is valid only for this unit.
    if device['device_id'] != '8032AB45611198F1':
        raise ValueError('identity mismatch')
    keys = c.keys_for(device)
    old_aes = {k['sha256'] for k in aes['key_manifest']}
    old_gap = {k['sha256'] for k in gap['key_manifest']}
    six = old_gap-old_aes
    # Reconstruct old keys with their original metadata when absent in the selected record.
    from scio import corpus
    old_record = corpus.load_record(gap['scan_paths'][0])
    old_record.device.update(KNOWN_IDENTITY)
    for key, labels in c.cipher_gap.build_keys(old_record.device).items():
        keys.setdefault(key, []).extend(labels)
    groups = {'1-six-aes': [], '2-identity-gap': [], '3-layered-coverage': []}
    for key in sorted(keys):
        kh = r.sha(key)
        for config in c.configs(key):
            if config[0] == 'AES':
                if kh in six:
                    stage = '1-six-aes'
                elif kh not in old_aes:
                    stage = '2-identity-gap'
                else:
                    # Existing AES codec coverage lacked bzip2/xz and two-role screening.
                    stage = '3-layered-coverage'
            else:
                stage = '3-layered-coverage' if kh in old_gap else '2-identity-gap'
            groups[stage].append((key, config, stage))
    selected = [first]
    for row in rows:
        if row['acquisition_group'] not in {x['acquisition_group'] for x in selected}:
            selected.append(row)
        if len(selected) == 3:
            break
    blobs = [first['blobs']['sample'], first['blobs']['sample_dark']]
    for row in selected[1:]:
        blobs.extend(row['blobs'][role] for role in ('sample', 'sample_dark', 'sample_gradient', 'sample_white', 'sample_white_dark') if role in row['blobs'])
    jobs = sum(groups.values(), [])
    # Deterministic controls use the identical configurations and evaluation path.
    rng = c.random.Random(7319)
    for i in range(16):
        key = rng.randbytes((16, 24, 32)[i % 3])
        jobs.extend((key, config, '4-random-key-controls') for config in c.configs(key))
        jobs.extend((key, config, '5-random-body-controls') for config in c.configs(key))
    manifest = dict(schema='scio-bounded-campaign/1',
        git_revision=subprocess.check_output(['git','rev-parse','HEAD'], text=True).strip(),
        device_id=device['device_id'], generation=first['device'].get('i2s_tag_config'),
        selected_records=[x['source'] for x in selected],
        input_hash=c.digest([r.sha(b) for b in blobs]), blob_hashes=[r.sha(b) for b in blobs],
        frozen_policy='Only historical canonical acquisitions before 2026-10-03; no frozen files loaded',
        prior_hashes={str(p): r.sha(p.read_bytes()) for p in (aes_path, gap_path)},
        selected_file_hashes={x['source']:r.sha(Path(x['source']).read_bytes()) for x in selected},
        code_hashes={r.label(p): r.sha(p.read_bytes()) for p in [Path(__file__), Path(c.__file__), Path(c.keyrecover.__file__), Path(c.search_v2.__file__), Path(c.cipher_gap.__file__)]},
        key_manifest=[dict(sha256=r.sha(k), derivations=sorted(set(v))) for k,v in keys.items()],
        configurations=[dict(key_sha256=r.sha(k), config=conf, stage=stage) for k,conf,stage in jobs],
        counts={s:len(v) for s,v in groups.items()}, six_missing_aes_keys=sorted(six),
        prior_coverage_limits='Non-AES reports save best configurations only; detailed attempted outcomes incomplete. New codec stage deliberately revisits these configurations.',
        validated_decoder=False)
    return manifest, jobs, blobs


def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--mode', choices=['plan','synthetic-test','offline-run'], default='plan')
    ap.add_argument('--output', default='dev/analysis_output/bounded_identity_20261004')
    ap.add_argument('--max-jobs', type=int)
    a=ap.parse_args()
    socket.socket.connect=deny; socket.socket.connect_ex=deny; socket.create_connection=deny
    if a.mode == 'synthetic-test':
        import pytest
        return pytest.main(['dev/tests/test_bounded_campaign.py','-q','-o','cache_dir=dev/.pytest_cache','--basetemp=dev/.pytest_tmp_bounded'])
    directory=c.output_dir(a.output)
    manifest,jobs,blobs=prepare()
    print(json.dumps({'counts':manifest['counts'], 'total':len(jobs), 'keys':len(manifest['key_manifest'])}), flush=True)
    if a.mode == 'plan':
        r.write_new(directory/'plan.json',manifest)
        return 0
    before=r.snapshot()
    c.run_jobs(directory,manifest,jobs,blobs,max_jobs=a.max_jobs)
    after=r.snapshot()
    if before != after:
        raise RuntimeError('source/production file hash changed')
    db=sqlite3.connect(directory/'results.sqlite')
    counts={}; leads=[]
    for index,stage,result in db.execute('SELECT job,stage,result FROM results'):
        data=json.loads(result); tag=stage+':'+data['status']; counts[tag]=counts.get(tag,0)+1
        if data['status']=='codec_lead': leads.append({'job':index,'stage':stage,'result':data})
    count=db.execute('SELECT COUNT(*) FROM results').fetchone()[0]; db.close()
    r.write_new(directory/f'summary_{count}.json', dict(completed=count,total=len(jobs),counts=counts,
        codec_leads=leads,source_hashes_unchanged=True,validated_decoder=False,
        limits='Codec parses are unvalidated. No arbitrary custom compression or unknown keys excluded. Frozen cap scans untouched.'))
    return 0

if __name__=='__main__':
    raise SystemExit(main())
