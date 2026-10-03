"""Six-request intact-blob composition test with predeclared numerical predictions."""
import argparse
import json
from pathlib import Path
import numpy as np
import _bootstrap
from scio_offline import research as r
from oracle_v2 import run_jobs


def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--live',action='store_true');a=p.parse_args()
    old=r.DEV/'analysis_output/recovery_20261003/oracle_network'
    requests={};spectra={}
    for path in old.glob('*_request.json'):
        request=json.loads(path.read_text());response=json.loads(path.with_name(path.name.replace('_request','_response')).read_text())
        requests[request['name']]=request
        if response['status']==200 and response['spectrum'] is not None:spectra[request['name']]=np.asarray(response['spectrum'])
    base=requests['control_initial']['payload'];r0=spectra['control_initial']
    if np.any(r0==0):raise ValueError('zero baseline; division prediction unsupported')
    roles={'s':'sample','w':'sample_white','d':'sample_white_dark'}
    jobs=[{'name':'control_initial','payload':base,'changes':{},'expected_spectrum':r0.tolist()}]
    for combination in ('sw','sd','wd','swd'):
        payload=dict(base)
        for letter in combination:
            role=roles[letter];payload[role]=requests[role+'_intact_substitution']['payload'][role]
        jobs.append({'name':'compose_'+combination,'payload':payload,
                     'changes':{roles[k]:{'operation':'previously accepted intact substitution'} for k in combination}})
    jobs.append({'name':'control_final','payload':base,'changes':{},'expected_spectrum':r0.tolist()})
    rs=spectra['sample_intact_substitution'];rw=spectra['sample_white_intact_substitution'];rd=spectra['sample_white_dark_intact_substitution']
    predictions={'compose_sw':rs*rw/r0,'compose_sd':rs*rd/r0}
    r.write_new(a.output/'predictions.json',{'fixed_before_requests':predictions,
        'conditional_prediction':'compose_swd = sample_single * compose_wd / control_initial',
        'gate':{'atol':1e-6,'rtol':1e-6},'limits':'Tests sample/white separability only. Does not recover blob plaintext or absolute domain scales.'})
    run_jobs(a.output,jobs,a.live)
    if not a.live or (a.output/'halt.json').exists():return
    responses={json.loads(path.read_text())['name']:json.loads(path.read_text()) for path in a.output.glob('*_response.json')}
    if any(row['status']!=200 or row['spectrum'] is None for row in responses.values()):
        r.write_new(a.output/'comparison.json',{'valid':False,'reason':'At least one combination did not yield a valid spectrum.'});return
    predictions['compose_swd']=rs*np.asarray(responses['compose_wd']['spectrum'])/r0
    comparisons={}
    for name,predicted in predictions.items():
        actual=np.asarray(responses[name]['spectrum']);delta=np.abs(actual-predicted)
        comparisons[name]={'equivalent':bool(np.allclose(actual,predicted,atol=1e-6,rtol=1e-6)),
            'max_absolute_error':float(delta.max()),'max_relative_error':float((delta/np.maximum(np.abs(predicted),1e-15)).max())}
    r.write_new(a.output/'comparison.json',{'valid':True,'comparisons':comparisons,
        'limits':'Even agreement across all bands only supports separability for these intact inputs, endpoint and generation. Absolute sample/white scale remains unidentified.'})
    print(json.dumps(comparisons))


if __name__=='__main__':main()
