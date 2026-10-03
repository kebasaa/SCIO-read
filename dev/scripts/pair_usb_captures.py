"""Obtain reference spectra for fresh cap captures, without production writes."""
import argparse
import base64
from datetime import datetime
import json
from pathlib import Path
import _bootstrap
from scio import session,cloud
from scio_offline import research as r
from oracle_v2 import run_jobs


def main():
    p=argparse.ArgumentParser(); p.add_argument('--input',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--live',action='store_true');a=p.parse_args()
    captured=json.loads(a.input.read_text()); device=captured['device']; rows=r.contexts()
    matches=[x for x in rows if x['device'].get('device_id')==device['device_id'] and x['device'].get('firmware_version')==device['firmware_version']]
    tags={x['device'].get('i2s_tag_config') for x in matches if x['device'].get('i2s_tag_config')}
    if len(tags)!=1:raise ValueError('no unique historically supported tag')
    tag=device.get('i2s_tag_config') or next(iter(tags))
    captures=captured['captures']
    if not 1<=len(captures)<=6 or any(c['status_word']!=0 for c in captures):raise ValueError('invalid captures')
    first={k:base64.b64decode(v) for k,v in captures[0]['blobs_b64'].items()}
    white={k.replace('sample','sample_white',1):v for k,v in first.items()}
    stamp=datetime.fromtimestamp(a.input.stat().st_mtime).astimezone().isoformat()
    control=session.to_payload(matches[0]['record'])
    jobs=[{'name':'control_initial','payload':control,'changes':{}}]
    for i,c in enumerate(captures):
        blobs={k:base64.b64decode(v) for k,v in c['blobs_b64'].items()}
        payload=cloud.build_scan_payload({'blobs':blobs},{'blobs':white},device['device_id'],tag,sampled_at=stamp,sampled_white_at=stamp)
        jobs.append({'name':f'fresh_cap_{i:02d}','payload':payload,'changes':{'source_capture':i,'white_capture':0}})
    jobs.append({'name':'control_final','payload':control,'changes':{}})
    r.write_new(a.output/'capture_provenance.json',{'source':r.label(a.input),'source_sha256':r.sha(a.input.read_bytes()),
        'physical_target':'User confirmed stationary in calibration cap','white_reference_capture':0,
        'original_i2s_tag':device.get('i2s_tag_config'),'request_i2s_tag':tag,
        'tag_basis':'Historical same-device and firmware records; missing live tag preserved, not silently repaired.',
        'timestamp_basis':'Capture-file modification time after batch; individual exposure times unavailable.',
        'evaluation_policy':'Prospective reference set. Do not tune candidate algorithms to these response values.'})
    run_jobs(a.output,jobs,a.live)


if __name__=='__main__':main()
