"""Derive an exploratory self-response factor without relabeling it as plaintext."""
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
    rows={};starts=[];evidence=[]
    for path in sorted(a.run.glob('*_response.json')):
        d=json.loads(path.read_text());q=path.with_name(path.name.replace('_response','_request'));request=json.loads(q.read_text())
        starts.append(datetime.fromisoformat(request['started_at']))
        if d['status']==200:
            axis,y=cloud.spectrum_from_response(d['response'])
            if not np.array_equal(axis,np.arange(740,1071)) or len(y)!=331 or not np.isfinite(y).all():raise ValueError('invalid spectrum')
            rows[d['name']]=np.asarray(y)
        evidence.append({'response':r.label(path),'sha256':r.sha(path.read_bytes()),'request_sha256':r.sha(q.read_bytes())})
    c=rows['self_sample'];other=rows['self_white'];predicted=c*c/rows['control_initial']
    report={'classification':'Exploratory server-derived self-response factor, NOT decoded sample/white values.',
        'wavelength_nm':np.arange(740,1071),'factor':c,'inverse_factor':1/c,
        'self_pair_max_absolute_difference':float(np.max(np.abs(c-other))),
        'corrected_reciprocal_prediction':'R(B,A) = C(lambda)^2 / R(A,B)',
        'corrected_reciprocal_max_absolute_error':float(np.max(np.abs(rows['reciprocal']-predicted))),
        'corrected_reciprocal_equivalent_at_1e_minus_10':bool(np.allclose(rows['reciprocal'],predicted,atol=1e-10,rtol=1e-10)),
        'request_count':len(starts),'minimum_request_start_gap_seconds':min((b-a).total_seconds() for a,b in zip(starts,starts[1:])),
        'controls_equivalent':all(np.allclose(rows[name],rows['control_initial'],atol=1e-6,rtol=1e-6) for name in ('control_middle','control_final')),
        'evidence':evidence,'limits':'C inferred from two self-reference pairs with fixed device/tag. Corrected reciprocity is a post-observation hypothesis check, not the predeclared unity/reciprocity test. Calibration interpretation and applicability to other devices/tags remain unproven; absolute domain scale remains unidentified.'}
    r.write_new(a.output,report)
    print(json.dumps({k:v for k,v in report.items() if k not in ('factor','inverse_factor','wavelength_nm','evidence')}))


if __name__=='__main__':main()
