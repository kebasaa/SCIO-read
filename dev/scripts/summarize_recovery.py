"""Summarize immutable evidence without running the device or contacting a server."""
import argparse
import json
from pathlib import Path
import numpy as np
import _bootstrap
from scio_offline import research as r, malleability


def oracle(folder):
    paths=sorted(folder.glob('*_response.json'))
    if not paths: return {'requests':0}
    baselines={}; rows=[]; observations=[]
    for path in paths:
        rec=json.loads(path.read_text()); request=json.loads(path.with_name(path.name.replace('_response','_request')).read_text())
        group=request.get('control_group','primary')
        if rec['name'].startswith('control') and group not in baselines:
            baselines[group]=rec['spectrum']
        change=malleability.delta(baselines.get(group),rec['spectrum'])
        rows.append({'name':rec['name'],'status':rec['status'],'delta':change,
            'response_without_spectrum':{k:v for k,v in rec['response'].items() if k!='spectrum'}})
        if not rec['name'].startswith('control'):
            observations.append(malleability.Observation(rec['name'],'coverage',request['changes'],rec['status'],rec['spectrum'],'',change))
    return {'requests':len(paths),'observations':rows,'classifier':malleability.classify(observations),
            'limits':'Coverage probes do not supply the bit ladders needed for confident transform classification. Zero effects constrain only this endpoint, generation and baseline.'}


def main():
    p=argparse.ArgumentParser(); p.add_argument('--run',type=Path,required=True); p.add_argument('--output',required=True); a=p.parse_args()
    before=json.loads((a.run/'input_snapshot.json').read_text()); after=r.snapshot()
    changes=sorted(k for k in set(before)|set(after) if before.get(k)!=after.get(k))
    report={'input_changes':changes,'oracle':oracle(a.run/'oracle_network')}
    if (a.run/'oracle_gradient_followup').exists():
        report['gradient_followup']=oracle(a.run/'oracle_gradient_followup')
    report['searches']={}
    for name in ('key_search_confirmed.json','key_search_foreign.json','key_search_images.json'):
        if (a.run/name).exists():
            groups=json.loads((a.run/name).read_text())['groups']
            report['searches'][name]=[{'device_id':g['device_id'],'i2s_tag':g['i2s_tag'],'attempted':g['attempted'],
                'keys':g['unique_keys'],'heuristic_leads':sum(c['heuristic_lead'] for c in g['top_candidates']),
                'consistent_codec_hits':sum(bool(c.get('consistent_codec_parameters')) for c in g['codec_hits'])} for g in groups]
    r.write_new(a.output,report)
    print(json.dumps({'input_changes':len(changes),'oracle_requests':report['oracle']['requests'],'searches':report['searches']}))


if __name__=='__main__': main()
