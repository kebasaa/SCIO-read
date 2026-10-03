"""Offline per-band and pacing verification of the six-request composition test."""
import argparse
from datetime import datetime
import json
from pathlib import Path
import numpy as np
import _bootstrap
from scio import cloud
from scio_offline import research as r


def main():
    p=argparse.ArgumentParser();p.add_argument('--run',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if (a.run/'halt.json').exists():raise ValueError('campaign halted; inspect halt before comparison')
    files=sorted(a.run.glob('*_request.json'))
    if len(files)!=6:raise ValueError('requires completed six-request campaign')
    starts=[];ends=[];responses={};evidence=[]
    for path in files:
        request=json.loads(path.read_text());rp=path.with_name(path.name.replace('_request','_response'));response=json.loads(rp.read_text())
        axis,values=cloud.spectrum_from_response(response['response'])
        values=np.asarray(values)
        if response['status']!=200 or values.shape!=(331,) or not np.isfinite(values).all() or not np.array_equal(axis,np.arange(740,1071)):
            raise ValueError('invalid response or wavelength axis')
        responses[request['name']]=values
        starts.append(datetime.fromisoformat(request['started_at']));ends.append(datetime.fromisoformat(response['finished_at']))
        evidence.append({'request':r.label(path),'request_sha256':r.sha(path.read_bytes()),'response':r.label(rp),'response_sha256':r.sha(rp.read_bytes())})
    predictions=json.loads((a.run/'predictions.json').read_text())
    old=r.DEV/'analysis_output/recovery_20261003/oracle_network'
    historical={json.loads(path.read_text())['name']:json.loads(path.read_text())['spectrum'] for path in old.glob('*_response.json')}
    expected={name:np.asarray(v) for name,v in predictions['fixed_before_requests'].items()}
    expected['compose_swd']=np.asarray(historical['sample_intact_substitution'])*responses['compose_wd']/np.asarray(historical['control_initial'])
    comparisons={}
    for name,prediction in expected.items():
        actual=responses[name];signed=actual-prediction
        good=np.isclose(actual,prediction,atol=1e-6,rtol=1e-6)
        comparisons[name]={'all_bands_equivalent':bool(good.all()),'failed_bands':int((~good).sum()),
            'max_absolute_error':float(np.abs(signed).max()),'rmse':float(np.sqrt(np.mean(signed**2))),
            'relative_error_denominator_floor':1e-15,
            'per_band_signed_error':signed,'per_band_relative_error':np.abs(signed)/np.maximum(np.abs(prediction),1e-15),
            'equivalent_at_1e_minus_10':bool(np.allclose(actual,prediction,atol=1e-10,rtol=1e-10))}
    gaps=[(b-a).total_seconds() for a,b in zip(starts,starts[1:])]
    idle=[(b-a).total_seconds() for a,b in zip(ends,starts[1:])]
    controls={name:bool(np.allclose(responses[name],historical['control_initial'],atol=1e-6,rtol=1e-6)) for name in ('control_initial','control_final')}
    r.write_new(a.output,{'evidence':evidence,'wavelength_nm':list(range(740,1071)),
        'all_six_responses_valid':True,'controls_equivalent_to_historical':controls,
        'request_start_gaps_seconds':gaps,'response_to_next_start_gaps_seconds':idle,
        'comparisons':comparisons,'limits':'No fitted rescaling. One historical baseline and its intact component substitutions; not a claim of plaintext recovery or absolute domain values.'})
    print(json.dumps({'minimum_start_gap':min(gaps),'minimum_idle_gap':min(idle),'controls':controls,
        'comparisons':{k:{a:b for a,b in v.items() if not a.startswith('per_band')} for k,v in comparisons.items()}}))


if __name__=='__main__':main()
