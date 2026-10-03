"""At most eight intact-blob requests; exact symmetry and dark-model predictions."""
import argparse
import json
from pathlib import Path
import numpy as np
import _bootstrap
from scio_offline import research as r
from oracle_v2 import run_jobs


def saved(folder):
    return {d['name']:d for p in folder.glob('*_response.json') if (d:=json.loads(p.read_text()))}


def compare(actual,expected):
    actual=np.asarray(actual);expected=np.asarray(expected);error=actual-expected
    return {'equivalent':bool(np.allclose(actual,expected,atol=1e-6,rtol=1e-6)),
        'failed_bands':int((~np.isclose(actual,expected,atol=1e-6,rtol=1e-6)).sum()),
        'max_absolute_error':float(np.abs(error).max()),'per_band_signed_error':error}


def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--live',action='store_true');a=p.parse_args()
    old=r.DEV/'analysis_output/recovery_20261003/oracle_network'
    req={d['name']:d for p in old.glob('*_request.json') if (d:=json.loads(p.read_text()))}
    truth=saved(old);base=req['control_initial']['payload'];r0=np.asarray(truth['control_initial']['spectrum'])
    rs=np.asarray(truth['sample_intact_substitution']['spectrum'])
    rw=np.asarray(truth['sample_white_intact_substitution']['spectrum'])
    rd=np.asarray(truth['sample_white_dark_intact_substitution']['spectrum'])
    rwd=np.asarray(saved(r.DEV/'analysis_output/recovery_20261003_followup/separability_live')['compose_wd']['spectrum'])
    if any(np.any(x==0) for x in (r0,rw,rd,rwd)):raise ValueError('zero denominator')
    # White-side additive test is already fully determined; do not resend it.
    white_test=compare(1/rwd-1/rw,1/rd-1/r0)
    white_test['effect_max']=float(np.max(np.abs(1/rd-1/r0)))
    r.write_new(a.output/'existing_white_additivity.json',white_test)
    jobs=[]
    def control(name):jobs.append({'name':name,'payload':base,'changes':{},'expected_spectrum':r0.tolist()})
    control('control_initial')
    for name,operation in [('self_sample','sample_to_white'),('self_white','white_to_sample'),('reciprocal','exchange')]:
        payload=dict(base)
        for suffix in ('','_dark','_gradient'):
            s='sample'+suffix;w='sample_white'+suffix
            if operation in ('sample_to_white','exchange'):payload[w]=base[s]
            if operation in ('white_to_sample','exchange'):payload[s]=base[w]
        if 'sampled_at' in base and 'sampled_white_at' in base:
            if operation in ('sample_to_white','exchange'):payload['sampled_white_at']=base['sampled_at']
            if operation in ('white_to_sample','exchange'):payload['sampled_at']=base['sampled_white_at']
        jobs.append({'name':name,'payload':payload,'changes':{'intact_triplets':operation,'timestamps':'moved with triplets when present'}})
    control('control_middle')
    if base['sample_dark']==base['sample_white_dark']:raise ValueError('dark alternative not distinct')
    for name,sample in [('dark_s0',base['sample']),('dark_s1',req['sample_intact_substitution']['payload']['sample'])]:
        payload=dict(base);payload['sample']=sample;payload['sample_dark']=base['sample_white_dark']
        job={'name':name,'payload':payload,'changes':{'sample_dark':'original intact white dark','sample':'original' if name=='dark_s0' else 'previously accepted intact alternative'}}
        if name=='dark_s1':job['requires_valid_spectrum']='dark_s0'
        jobs.append(job)
    control('control_final')
    r.write_new(a.output/'hypotheses.json',{'maximum_analysis_requests':8,'minimum_spacing_seconds':20,
        'self_reference':'all ones','reciprocity':'reciprocal = 1 / historical control',
        'sample_dark_additivity':'dark_s1 - historical sample-single = dark_s0 - historical control',
        'dark_choice':'Original same-device white dark, not the previously rejected alternative sample dark.',
        'limits':'No fresh holdout data. Failures constrain these intact combinations only. No absolute domain recovery.'})
    run_jobs(a.output,jobs,a.live)
    if not a.live or (a.output/'halt.json').exists():return
    responses=saved(a.output);comparisons={}
    def valid(name):return name in responses and responses[name]['status']==200 and responses[name]['spectrum'] is not None
    for name,prediction in [('self_sample',np.ones(331)),('self_white',np.ones(331)),('reciprocal',1/r0)]:
        comparisons[name]=compare(responses[name]['spectrum'],prediction) if valid(name) else {'testable':False,'reason':'No valid spectrum; not a numerical falsification'}
    if valid('dark_s0') and valid('dark_s1'):
        comparisons['sample_dark_additivity']=compare(np.asarray(responses['dark_s1']['spectrum'])-rs,np.asarray(responses['dark_s0']['spectrum'])-r0)
    else:comparisons['sample_dark_additivity']={'testable':False,'reason':'No complete valid dark grid'}
    r.write_new(a.output/'comparison.json',comparisons)
    print(json.dumps({k:{a:b for a,b in v.items() if not a.startswith('per_band')} for k,v in comparisons.items()}))


if __name__=='__main__':main()
