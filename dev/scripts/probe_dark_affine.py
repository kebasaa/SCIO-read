"""Seven-request test of a frozen dark-change model on two additional samples."""
import argparse
from datetime import datetime
import json
from pathlib import Path
import numpy as np
import _bootstrap
from scio import session
from scio_offline import research as r
from scio_offline.response_models import affine_from_two,comparison
from oracle_v2 import run_jobs


def named(folder,suffix):
    return {d['name']:d for p in folder.glob('*_'+suffix+'.json') if (d:=json.loads(p.read_text()))}


def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--live',action='store_true');a=p.parse_args()
    old=r.DEV/'analysis_output/recovery_20261003/oracle_network';previous=r.DEV/'analysis_output/recovery_20261003_followup/symmetry'
    req=named(old,'request');truth=named(old,'response');dark=named(previous,'response')
    base=req['control_initial']['payload'];x0=np.asarray(truth['control_initial']['spectrum']);x1=np.asarray(truth['sample_intact_substitution']['spectrum'])
    slope,offset=affine_from_two(x0,x1,dark['dark_s0']['spectrum'],dark['dark_s1']['spectrum'])
    c=json.loads((previous/'self_response_factor.json').read_text())['factor']
    held=set(json.loads((r.DEV/'analysis_output/recovery_20261003/corpus_final.json').read_text())['confirmation_ids'])
    sources=('20200604143505_20200604_dead_needles_log01_spectrum.json','20200604143557_soilcrust_143557_spectrum.json')
    rows=r.contexts();selected=[]
    for source in sources:
        row=next(x for x in rows if Path(x['source']).name==source)
        if row['id'] in held:raise ValueError('would consume frozen confirmation record')
        payload=session.to_payload(row['record'])
        for key in ('device_id','i2s_tag_config'):
            if payload.get(key)!=base.get(key):raise ValueError('device/tag mismatch')
        if payload['sample'] in (base['sample'],req['sample_intact_substitution']['payload']['sample']):raise ValueError('not independent sample blob')
        selected.append((row,payload['sample']))
    provenance=[{'source':row['source'],'id':row['id'],'sample_sha256':r.sha(row['blobs']['sample'])} for row,_ in selected]
    r.write_new(a.output/'frozen_hypotheses.json',{'slope':slope,'offset':offset,'conditional_prediction':'changed_dark = slope * baseline_dark + offset',
        'self_prediction':c,'selected':provenance,'maximum_requests':7,'minimum_spacing_seconds':20,
        'limits':'Two-point per-band fit is tautological on fit samples; only new combinations test generalization. This model is not a decoder or proof of physical dark subtraction. Fresh and retrospective confirmation sets excluded.'})
    jobs=[{'name':'control_initial','payload':base,'changes':{},'expected_spectrum':x0.tolist()}]
    for index,(_,sample) in enumerate(selected):
        for mode in ('d0','d1'):
            payload=dict(base);payload['sample']=sample
            if mode=='d1':payload['sample_dark']=base['sample_white_dark']
            job={'name':f'new{index}_{mode}','payload':payload,'changes':{'sample_source':provenance[index]['source'],'dark':mode}}
            if mode=='d1':job['requires_valid_spectrum']=f'new{index}_d0'
            jobs.append(job)
        if index==0:
            payload=dict(base);payload['sample']=sample
            for suffix in ('','_dark','_gradient'):payload['sample_white'+suffix]=payload['sample'+suffix]
            if 'sampled_at' in payload:payload['sampled_white_at']=payload['sampled_at']
            jobs.append({'name':'new0_self','payload':payload,'changes':{'intact_pair':'same on both sides'},'requires_valid_spectrum':'new0_d0'})
    jobs.append({'name':'control_final','payload':base,'changes':{},'expected_spectrum':x0.tolist()})
    run_jobs(a.output,jobs,a.live)
    if not a.live or (a.output/'halt.json').exists():return
    responses=named(a.output,'response');results={}
    def valid(name):return name in responses and responses[name]['status']==200 and responses[name]['spectrum'] is not None
    for i in range(2):
        first,second=f'new{i}_d0',f'new{i}_d1'
        results[f'new{i}_affine']=comparison(responses[second]['spectrum'],slope*np.asarray(responses[first]['spectrum'])+offset) if valid(first) and valid(second) else {'testable':False}
    results['new0_self']=comparison(responses['new0_self']['spectrum'],c) if valid('new0_self') else {'testable':False}
    starts=[datetime.fromisoformat(json.loads(p.read_text())['started_at']) for p in sorted(a.output.glob('*_request.json'))]
    r.write_new(a.output/'comparison.json',{'results':results,'requests_sent':len(starts),'minimum_request_start_gap_seconds':min((b-a).total_seconds() for a,b in zip(starts,starts[1:]))})
    print(json.dumps({k:{a:b for a,b in v.items() if not a.startswith('per_band')} for k,v in results.items()}))


if __name__=='__main__':main()
