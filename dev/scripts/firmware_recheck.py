"""Three bounded GETs to the app-established firmware endpoint; never installs."""
import argparse
import contextlib
import io
import json
import time
from pathlib import Path
import requests
import _bootstrap
from scio import credentials,cloud
from scio_offline import research as r
from scio_offline.firmware_containers import NAMES,decode_candidate


def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True)
    p.add_argument('--live',action='store_true');a=p.parse_args()
    out=a.output.resolve()
    if not out.is_relative_to(r.DEV) or out.exists():raise ValueError('new output directory under dev required')
    device=json.loads((r.ROOT/'01_rawdata/device_files/device_20260907_155207.json').read_text())
    identity=device['device'];current={f"0x{x['file_type']:02X}":f"0x{x['file_version']:02X}" for x in device['file_list'] if 87<=x['file_type']<=95}
    lower={key:f'0x{max(1,int(value,16)-1):02X}' for key,value in current.items()}
    jobs=[('current_control',current),('one_below',lower),('current_control_final',current)]
    r.write_new(out/'plan.json',{'device_ble_id':identity['ble_id'].upper(),'compression_version':identity['i2s_tag_config'],
        'source_metadata':'01_rawdata/device_files/device_20260907_155207.json','jobs':jobs,
        'max_requests':3,'min_gap_seconds':20,'scope':'Known GET firmware-upgrade only. Availability recheck, not a new version-search family. No device writes.'})
    if not a.live:return
    try:
        with contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):
            token=credentials.get_token(prompt_if_needed=False)
    except Exception as exc:
        r.write_new(out/'halt.json',{'reason':'authentication unavailable','exception_type':type(exc).__name__});print('Authentication unavailable');return
    last=0;results=[]
    private=r.DEV/'private'/out.name;private.mkdir(parents=True,exist_ok=False)
    for index,(name,versions) in enumerate(jobs):
        time.sleep(max(0,20-(time.monotonic()-last)))
        params={'versions':json.dumps([{'key':k,'value':v} for k,v in versions.items()],separators=(',',':')),
                'compression_version':identity['i2s_tag_config']}
        last=time.monotonic()
        row={'name':name,'versions':versions,'started_unix':time.time()}
        try:
            with requests.get(cloud.API_BASE+'/device/'+identity['ble_id'].upper()+'/firmware-upgrade',params=params,
                headers={'Authorization':'Bearer '+token,'Accept':'application/json','X-SCiO-Client-Version':'Android 1.3.8.554'},
                timeout=30,allow_redirects=False,stream=True) as response:
                row['status']=response.status_code;chunks=[];size=0
                for chunk in response.iter_content(65536):
                    size+=len(chunk)
                    if size>32*1024*1024:raise ValueError('response size cap')
                    chunks.append(chunk)
                raw=b''.join(chunks)
            with (private/f'{index:02d}_response.bin').open('xb') as f:f.write(raw)
            row.update({'response_sha256':r.sha(raw),'response_bytes':len(raw)})
            if row['status']!=200:raise ValueError('non-success status')
            obj=json.loads(raw)
            if not isinstance(obj,dict) or 'new_version' not in obj:raise ValueError('unexpected response schema')
            offered=obj['new_version'];row['new_version_is_null']=offered is None;row['files']=[]
            if offered is not None and not isinstance(offered,dict):raise ValueError('unexpected payload map')
            for key,value in (offered or {}).items():
                if key not in NAMES:raise ValueError('unexpected firmware file name')
                data=decode_candidate(value)
                if data is None:raise ValueError('invalid offered blob')
                with (private/(key+'.container')).open('xb') as f:f.write(data)
                row['files'].append({'name':key,'container_sha256':r.sha(data),'body_sha256':r.sha(data[4:]),
                    'body_bytes':len(data)-4,'prefix_u32le':int.from_bytes(data[:4],'little')})
        except Exception as exc:
            row['halt_exception_type']=type(exc).__name__
        row['elapsed_monotonic_seconds']=time.monotonic()-last
        # Cool down after completion, avoiding start-time bookkeeping jitter.
        last=time.monotonic()
        r.write_new(out/f'{index:02d}_{name}.json',row);results.append(row)
        print(name,'status',row.get('status'),'offered',len(row.get('files',[])),flush=True)
        if 'halt_exception_type' in row or row.get('files'):break
    r.write_new(out/'summary.json',{'results':results,'limits':'Null is only the observed offer for these parameters. Does not prove firmware deleted or unavailable to other authorized clients. No installation, reset or device command.'})


if __name__=='__main__':main()
