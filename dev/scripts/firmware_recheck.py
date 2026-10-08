"""Bounded GETs to the app-established firmware endpoint; never installs.

`main()` is the three-request availability recheck. `run_firmware_jobs` is the shared
transport, also used by `probe_old_firmware.py`.
"""
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
from scio_offline.firmware import parse_ldr
from scio_offline.firmware_containers import NAMES,decode_candidate

DEFAULT_CLIENT='Android 1.3.8.554'
DEVICE_FILE='01_rawdata/device_files/device_20260907_155207.json'
#: This unit's file headers (README section 5): name -> (size, version, checksum).
UNIT_HEADERS={'dsp_boot':(7284,17,688456),'dsp_dec':(14600,12,1548938),'dsp_op':(32628,147,4151168),
    'deadPixelsIndices':(1714,3,97267),'centers':(96,3,6080),'bins':(140,3,13587),'nPixelsPerBin':(1166,3,36371)}
LIMITS='Null is only the observed offer for these parameters. Does not prove firmware deleted or unavailable to other authorized clients. No installation, reset or device command.'


def device_identity():
    device=json.loads((r.ROOT/DEVICE_FILE).read_text())
    current={f"0x{x['file_type']:02X}":f"0x{x['file_version']:02X}" for x in device['file_list'] if 87<=x['file_type']<=95}
    return device['device'],current


def describe_body(name,data,extra_headers=None):
    """Metadata for an offered container (4-byte LE checksum prefix + body).

    ``extra_headers`` is an optional second header table ``name -> (size, version,
    checksum)`` (e.g. a foreign unit's) compared alongside this unit's fw-147 table.
    """
    body=data[4:]
    row={'name':name,'container_sha256':r.sha(data),'body_sha256':r.sha(body),
         'body_bytes':len(body),'prefix_u32le':int.from_bytes(data[:4],'little')}
    if name.startswith('dsp_'):
        ldr=parse_ldr(body);row['ldr_valid']=bool(ldr.get('valid_ldr'));row['ldr_blocks']=len(ldr.get('blocks',[]))
    if name in UNIT_HEADERS:
        size,version,checksum=UNIT_HEADERS[name]
        row['matches_unit_header_size']=len(body)==size
        row['matches_unit_header_checksum']=row['prefix_u32le']==checksum
    if extra_headers and name in extra_headers:
        size,version,checksum=extra_headers[name][:3]
        row['matches_foreign_header_size']=len(body)==size
        row['matches_foreign_header_checksum']=row['prefix_u32le']==checksum
    return row


def run_firmware_jobs(out,jobs,live,ble_id,default_tag,saved_dir=None,budget=None,compare_headers=None):
    """Send each job's GET serially; stop on any error or on the first offer.

    A job is {'name', 'versions', optional 'compression_version', optional 'client',
    optional 'ble_id'}. A per-job ``ble_id`` overrides the default (e.g. a control
    against the owner's own device within one serially-spaced run). ``compare_headers``
    is an optional second header table passed to :func:`describe_body`.
    Returns the result rows. Raw responses stay in dev/private/<run>; offered bodies
    are also written to ``saved_dir`` (git-ignored dev/recovered_firmware/<run>).
    """
    if budget is not None and len(jobs)>budget:raise ValueError('firmware jobs exceed request budget')
    r.write_new(out/'firmware_plan.json',{'device_ble_id':ble_id,'default_compression_version':default_tag,
        'source_metadata':DEVICE_FILE,'jobs':jobs,'max_requests':len(jobs),'min_gap_seconds':20,
        'scope':'Known GET firmware-upgrade only. No device writes, installation or reset.'})
    if not live:return []
    try:
        with contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):
            token=credentials.get_token(prompt_if_needed=False)
    except Exception as exc:
        r.write_new(out/'halt.json',{'reason':'authentication unavailable','exception_type':type(exc).__name__});print('Authentication unavailable');return []
    last=0;results=[]
    private=r.DEV/'private'/out.name;private.mkdir(parents=True,exist_ok=True)
    for index,job in enumerate(jobs):
        name=job['name'];versions=job['versions']
        tag=job.get('compression_version',default_tag);client=job.get('client',DEFAULT_CLIENT)
        req_ble=job.get('ble_id',ble_id)
        time.sleep(max(0,20-(time.monotonic()-last)))
        params={'versions':json.dumps([{'key':k,'value':v} for k,v in versions.items()],separators=(',',':'))}
        if tag is not None:params['compression_version']=tag
        last=time.monotonic()
        row={'name':name,'ble_id':req_ble,'versions':versions,'compression_version':tag,'client':client,'started_unix':time.time()}
        try:
            with requests.get(cloud.API_BASE+'/device/'+req_ble+'/firmware-upgrade',params=params,
                headers={'Authorization':'Bearer '+token,'Accept':'application/json','X-SCiO-Client-Version':client},
                timeout=30,allow_redirects=False,stream=True) as response:
                row['status']=response.status_code;chunks=[];size=0
                for chunk in response.iter_content(65536):
                    size+=len(chunk)
                    if size>32*1024*1024:raise ValueError('response size cap')
                    chunks.append(chunk)
                raw=b''.join(chunks)
            with (private/f'{index:02d}_{name}_response.bin').open('xb') as f:f.write(raw)
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
                if saved_dir is not None:
                    saved_dir.mkdir(parents=True,exist_ok=True)
                    with (saved_dir/(key+'.bin')).open('xb') as f:f.write(data[4:])
                    with (saved_dir/(key+'.checksum')).open('x') as f:f.write(str(int.from_bytes(data[:4],'little')))
                row['files'].append(describe_body(key,data,compare_headers))
        except Exception as exc:
            row['halt_exception_type']=type(exc).__name__
        row['elapsed_monotonic_seconds']=time.monotonic()-last
        # Cool down after completion, avoiding start-time bookkeeping jitter.
        last=time.monotonic()
        r.write_new(out/f'fw_{index:02d}_{name}.json',row);results.append(row)
        print(name,'status',row.get('status'),'offered',len(row.get('files',[])),flush=True)
        if 'halt_exception_type' in row or row.get('files'):break
    return results


def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True)
    p.add_argument('--live',action='store_true');a=p.parse_args()
    out=a.output.resolve()
    if not out.is_relative_to(r.DEV) or out.exists():raise ValueError('new output directory under dev required')
    identity,current=device_identity()
    lower={key:f'0x{max(1,int(value,16)-1):02X}' for key,value in current.items()}
    jobs=[{'name':'current_control','versions':current},{'name':'one_below','versions':lower},
          {'name':'current_control_final','versions':current}]
    results=run_firmware_jobs(out,jobs,a.live,identity['ble_id'].upper(),identity['i2s_tag_config'],budget=3)
    if a.live and results:r.write_new(out/'summary.json',{'results':results,'limits':LIMITS})


if __name__=='__main__':main()
