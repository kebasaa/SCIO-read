"""Plan, download or inspect a four-GET contributor firmware campaign."""
import argparse
import json
from pathlib import Path
import _bootstrap
from scio_offline import contributor_firmware as fw, research as r


def inspect(campaign, out):
    campaign=fw.inside_dev(campaign);out=fw.inside_dev(out)
    if out.exists(): raise FileExistsError('new inspection output required')
    plan=json.loads((campaign/'plan.json').read_text())
    summary=json.loads((campaign/'summary.json').read_text())
    profiles=plan['profiles']
    for profile in profiles: fw.validate_profile(profile)
    rows=[]
    for row in summary['rows']:
        path=row.get('private_response_path')
        if not path: continue
        source=fw.inside_dev(r.ROOT/path);raw=source.read_bytes()
        if r.sha(raw)!=row['response_sha256']:
            raise ValueError('archived response hash mismatch')
        reviewed={'name':row['name'],'status':row['status'],'response_sha256':r.sha(raw)}
        if row['status']==200 and not row.get('response_truncated'):
            private=fw.inside_dev(r.DEV/'private'/'contributor_inspection'/(out.name+'_'+r.sha(r.label(out).encode())[:8])/row['name'])
            try: reviewed.update(fw.inspect_response(raw,private,profiles))
            except (ValueError,TypeError) as exc:
                reviewed.update(halt_reason='malformed archive',exception_type=type(exc).__name__)
        rows.append(reviewed)
    r.write_new(out/'inspection.json',{'source_campaign':r.label(campaign),'rows':rows,'network_requests':0})
    print('Inspected',len(rows),'archived responses without network access')


def main():
    p=argparse.ArgumentParser();p.add_argument('--mode',choices=['plan-only','live-download','offline-inspection'],default='plan-only')
    p.add_argument('--profile',type=Path,default=Path('dev/profiles/contributor_fw138.json'))
    p.add_argument('--output',type=Path,required=True);p.add_argument('--campaign',type=Path)
    a=p.parse_args()
    if a.mode=='offline-inspection':
        if not a.campaign: p.error('--campaign required for inspection')
        inspect(a.campaign,a.output);return
    before=r.snapshot()
    profile=fw.load_profile(a.profile)
    result=fw.run(a.output,profile,live=a.mode=='live-download')
    unchanged=before==r.snapshot()
    r.write_new(a.output/'verification.json',{'source_and_production_hashes_unchanged':unchanged,
        'source_snapshot_sha256':r.sha(json.dumps(before,sort_keys=True).encode()),
        'mode':a.mode,'firmware_gets':result.get('firmware_gets',0)})
    if not unchanged: raise RuntimeError('source or production files changed')


if __name__=='__main__': main()
