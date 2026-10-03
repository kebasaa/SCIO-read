"""Corrected device/generation-specific search, with immutable output."""
import argparse
import json
import base64
from pathlib import Path
import _bootstrap
from scio_offline import research, search_v2
from scio import session


def main():
    p=argparse.ArgumentParser(); p.add_argument('--output',required=True); p.add_argument('--extended',action='store_true'); p.add_argument('--foreign',action='store_true')
    args=p.parse_args(); groups={}
    for path in ([] if args.foreign else sorted(Path('01_rawdata/scans').glob('*.json'))):
        rec=session.load_record(path); d=rec.get('device',{}); identity=(d.get('device_id'),d.get('i2s_tag_config'))
        g=groups.setdefault(identity,{'device':{},'blobs':{},'conflicts':{}})
        # Values must agree within a device/generation, never pool foreign IDs.
        for source in (d,d.get('device_info_raw') or {}):
            for k,v in source.items():
                if v is not None and v!='' and not isinstance(v,dict):
                    if k in g['device'] and g['device'][k]!=v:
                        g['conflicts'].setdefault(k,[]).append(v)
                    g['device'].setdefault(k,v)
        sample,_=session.record_blobs(rec); b=sample.get('sample_dark')
        if b:g['blobs'][research.sha(b)]=b
    if args.foreign:
        for path in sorted(Path('dev/analysis_output/foreign_scans').glob('*.json')):
            rec=json.loads(path.read_text()); identity=(rec.get('device_id'),rec.get('i2s_tag_config'))
            g=groups.setdefault(identity,{'device':{k:rec[k] for k in ('device_id','i2s_tag_config')},'blobs':{},'conflicts':{}})
            for role in ('sample_dark','sample_white_dark'):
                if role in rec.get('blobs_b64',{}):
                    b=base64.b64decode(rec['blobs_b64'][role]); g['blobs'][research.sha(b)]=b
    results=[]
    for identity,g in groups.items():
        print('Searching device/generation',identity,'unique dark blobs',len(g['blobs']),flush=True)
        keys=search_v2.candidate_keys(g['device'],args.extended)
        for field,values in g['conflicts'].items():
            for value in values:
                variant=dict(g['device']); variant[field]=value
                for key,names in search_v2.candidate_keys(variant,args.extended).items():
                    keys.setdefault(key,names)
        result=search_v2.search(list(g['blobs'].values()),keys,extended=args.extended)
        result['metadata_conflict_fields']=sorted(g['conflicts'])
        result['device_id'],result['i2s_tag']=identity; results.append(result)
    research.write_new(args.output,{'groups':results,'supersedes':'dark_rescreen.json: incorrect framing'})
    print(json.dumps({'groups':len(results),'attempts':sum(r['attempted'] for r in results),
                      'heuristic_leads':sum(c['heuristic_lead'] for r in results for c in r['top_candidates'])}))

if __name__=='__main__': main()
