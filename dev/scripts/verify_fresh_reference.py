"""Freeze fresh reference provenance without displaying or fitting spectral truth."""
import argparse
import base64
from datetime import datetime
import json
from pathlib import Path
import numpy as np
import _bootstrap
from scio import cloud
from scio_offline import research as r


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--run',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    records=[]; starts=[]; controls=[]
    for path in sorted(a.run.glob('*_response.json')):
        response=json.loads(path.read_text())
        request_path=path.with_name(path.name.replace('_response','_request'))
        request=json.loads(request_path.read_text())
        axis,values=cloud.spectrum_from_response(response['response'])
        axis=np.asarray(axis); values=np.asarray(values)
        valid=response['status']==200 and values.shape==(331,) and bool(np.isfinite(values).all()) and np.array_equal(axis,np.arange(740,1071))
        if not valid: raise ValueError('invalid fresh reference response')
        starts.append(datetime.fromisoformat(request['started_at']))
        if response['name'].startswith('control'): controls.append(values)
        records.append({'name':response['name'],'request':r.label(request_path),
            'request_sha256':r.sha(request_path.read_bytes()),'response':r.label(path),
            'response_sha256':r.sha(path.read_bytes()),'finite_331_correct_axis':valid})
    if len(records)!=8 or len(controls)!=2: raise ValueError('incomplete campaign')
    if not np.allclose(controls[0],controls[1],atol=1e-6,rtol=1e-6): raise ValueError('control drift')
    provenance=json.loads((a.run/'capture_provenance.json').read_text())
    captures=json.loads((r.ROOT/provenance['source']).read_text())['captures']
    blob_records=[{'capture':i,'role':role,'bytes':len(base64.b64decode(value)),
        'sha256':r.sha(base64.b64decode(value))} for i,scan in enumerate(captures) for role,value in scan['blobs_b64'].items()]
    before=json.loads((r.DEV/'analysis_output/recovery_20261003/input_snapshot.json').read_text())
    after=r.snapshot()
    changes=sorted(k for k in set(before)|set(after) if before.get(k)!=after.get(k))
    report={'records':records,'blobs':blob_records,'unique_blob_count':len({b['sha256'] for b in blob_records}),
        'minimum_request_start_gap_seconds':min((b-a).total_seconds() for a,b in zip(starts,starts[1:])),
        'control_numerical_equivalence':True,'production_input_changes':changes,
        'policy':'One acquisition/calibration group, not six independent calibration groups. All six spectra reserved for prospective confirmation. No fitting, rescaling, or vector inspection here.'}
    r.write_new(a.output,report)
    print(json.dumps({k:v for k,v in report.items() if k not in ('records','blobs')}))


if __name__=='__main__': main()
