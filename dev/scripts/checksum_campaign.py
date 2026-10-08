"""Network-disabled, dev-contained checksum hypothesis driver and artifact inspector."""
import argparse
import json
import socket
from pathlib import Path
import _bootstrap
from scio_offline import checksum_campaign as c, research as r, contributor_firmware as fw


def deny(*args,**kwargs):
    raise RuntimeError('network disabled for checksum campaign')


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--mode',choices=['plan-only','synthetic-test','offline-run','inspect-firmware'],default='plan-only')
    p.add_argument('--output',type=Path)
    p.add_argument('--max-jobs',type=int)
    p.add_argument('--artifact',type=Path)
    p.add_argument('--artifact-format',choices=['raw','container'],default='raw')
    p.add_argument('--name',choices=['ble','dsp_boot','dsp_dec','dsp_op','deadPixelsIndices','centers','bins','nPixelsPerBin'],default='dsp_boot')
    p.add_argument('--compare',type=Path)
    p.add_argument('--apps',type=Path,help='Optional local app material root for static audit')
    a=p.parse_args()
    socket.socket.connect=deny;socket.socket.connect_ex=deny;socket.create_connection=deny
    if a.mode=='synthetic-test':
        import pytest
        raise SystemExit(pytest.main(['dev/tests/test_checksum_campaign.py','-q','-o','cache_dir=dev/.pytest_cache','--basetemp=dev/.pytest_tmp_checksum_driver']))
    if not a.output: p.error('--output required')
    out=fw.inside_dev(a.output)
    before=r.snapshot()
    if a.mode=='inspect-firmware':
        if not a.artifact: p.error('--artifact required')
        c.inspect_artifacts(out,a.artifact,a.name,a.artifact_format,a.compare)
        summary={'mode':a.mode}
    else:
        manifest,jobs,groups=c.prepare()
        print('Unique hypothesis keys:',manifest['unique_hypothesis_keys'],'jobs:',len(jobs),
              'skipped prior configurations:',manifest['skipped_exact_owner_aes_configurations'],flush=True)
        if a.mode=='plan-only':
            r.write_new(out/'plan.json',manifest);summary={'mode':a.mode,'jobs':len(jobs)}
        else: summary=c.run(out,manifest,jobs,groups,max_jobs=a.max_jobs)
    if a.apps: c.audit_apps(a.apps,out)
    unchanged=before==r.snapshot()
    checkpoint=out/('verification_'+str(summary.get('completed','plan'))+'.json')
    if not checkpoint.exists(): r.write_new(checkpoint,{'source_and_production_hashes_unchanged':unchanged,
        'snapshot_sha256':r.sha(json.dumps(before,sort_keys=True).encode()),'network_blocked':True})
    if not unchanged: raise RuntimeError('source or production changed')


if __name__=='__main__': main()
