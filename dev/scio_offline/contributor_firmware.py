"""Bounded acquisition of contributor firmware; files and evidence stay in dev."""
from __future__ import annotations

import base64
import binascii
import contextlib
import io
import json
import re
import struct
import time
import zipfile
from pathlib import Path

import requests
from . import research as r
from .firmware import entropy, parse_ldr
from .firmware_containers import NAMES

CLIENT = 'Android 1.3.8.554'
KEYS = ('0x57', '0x5A', '0x5B', '0x5C')
MAX_RESPONSE = 32 * 1024 * 1024
GAP = 20
OWN = {
    'schema': 'scio-firmware-profile/1', 'profile_id': 'owner_fw147',
    'device_id': '8032AB45611198F1', 'ble_id': '01665900004C99B4',
    'i2s_tag_config': '20150812-e:PRODUCTION',
    'current_versions': dict(zip(KEYS, ('0x7D', '0x11', '0x0C', '0x93'))),
    'file_headers': {'ble': [87,119233,125,12925168], 'dsp_boot':[90,7284,17,688456],
        'dsp_dec':[91,14600,12,1548938], 'dsp_op':[92,32628,147,4151168],
        'deadPixelsIndices':[100,1714,3,97267], 'centers':[101,96,3,6080],
        'bins':[102,140,3,13587], 'nPixelsPerBin':[103,1166,3,36371]},
    'provenance': {'source': 'README.md section 5; previous verified device headers'},
}
IDENTITIES = {'owner_fw147': ('8032AB45611198F1','01665900004C99B4','20150812-e:PRODUCTION'),
              'contributor_fw138': ('E02E60F46B7CD55F','EBA03B00004C99B4','20150812:PRODUCTION')}


def validate_profile(profile):
    if profile.get('schema') != 'scio-firmware-profile/1':
        raise ValueError('invalid profile schema')
    expected = IDENTITIES.get(profile.get('profile_id'))
    actual = tuple(profile.get(k) for k in ('device_id','ble_id','i2s_tag_config'))
    if actual != expected or expected is None:
        raise ValueError('mixed or unsupported device identity')
    versions = profile['current_versions']
    if set(versions) != set(KEYS):
        raise ValueError('exactly four firmware version keys required')
    for key,value in versions.items():
        if not re.fullmatch(r'0x[0-9A-F]{2}',value):
            raise ValueError('invalid hexadecimal version')
        name = dict(zip(KEYS, ('ble','dsp_boot','dsp_dec','dsp_op')))[key]
        if int(value,16) != profile['file_headers'][name][2]:
            raise ValueError('versions disagree with device headers')
    for values in profile['file_headers'].values():
        if len(values)!=4 or any(type(v) is not int or v<0 or v>0xffffffff for v in values):
            raise ValueError('invalid file header')
    return profile


def load_profile(path):
    profile=validate_profile(json.loads(Path(path).read_text(encoding='utf-8')))
    source=(r.ROOT/profile['provenance']['source']).resolve()
    if not source.is_relative_to(r.ROOT):
        raise ValueError('source must be inside repository')
    profile['provenance']['source_sha256']=r.sha(source.read_bytes())
    profile['provenance']['profile_sha256']=r.sha(Path(path).read_bytes())
    return profile


def jobs_for(contributor):
    validate_profile(contributor); validate_profile(OWN)
    return [
        {'name':'owner_control_initial','profile':OWN,'versions':OWN['current_versions']},
        {'name':'contributor_actual','profile':contributor,'versions':contributor['current_versions']},
        {'name':'contributor_zero','profile':contributor,'versions':{k:'0x00' for k in KEYS}},
        {'name':'owner_control_final','profile':OWN,'versions':OWN['current_versions']},
    ]


def inside_dev(path):
    path=Path(path).resolve()
    if not path.is_relative_to(r.DEV.resolve()):
        raise ValueError('output must be under dev')
    return path


def save_bytes(path, data):
    path=inside_dev(path)
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('xb') as f:
        f.write(data)


def strict_container(value):
    if not isinstance(value,str):
        raise ValueError('firmware value must be Base64 text')
    compact=''.join(value.split())
    if not compact or len(compact)%4:
        raise ValueError('missing or invalid Base64 padding')
    try:
        raw=base64.b64decode(compact,validate=True)
    except (ValueError,binascii.Error) as exc:
        raise ValueError('invalid Base64') from exc
    if base64.b64encode(raw).decode()!=compact:
        raise ValueError('noncanonical Base64')
    if len(raw)<=4:
        raise ValueError('container must include prefix and body')
    return raw


def describe(name, raw, profiles):
    body=raw[4:]; prefix=struct.unpack('<I',raw[:4])[0]
    result={'name':name,'container_bytes':len(raw),'container_sha256':r.sha(raw),
        'body_bytes':len(body),'body_sha256':r.sha(body),'prefix_u32le':prefix,
        'unsigned_byte_sum':sum(body),'byte_sum_matches_prefix':sum(body)==prefix,
        'entropy_bits_per_byte':entropy(body),'header_comparisons':{},
        'checksum_algorithm_established':False}
    for profile in profiles:
        header=profile['file_headers'].get(name)
        if header:
            result['header_comparisons'][profile['profile_id']]={
                'reported_file_id':header[0],'reported_current_version':header[2],
                'matches_current_size':len(body)==header[1],
                'matches_current_checksum_field':prefix==header[3],
                'interpretation':'Comparison only: offered upgrade may differ from installed image'}
    if name.startswith('dsp_'):
        result['blackfin_ldr']=parse_ldr(body)
    result['wrapper_markers']=[label for label,magic in (
        ('gzip',b'\x1f\x8b'),('xz',b'\xfd7zXZ\x00'),('zip',b'PK\x03\x04'),('bzip2',b'BZh')) if body.startswith(magic)]
    if name=='ble':
        result['architecture_lead']='CC2540 uses 8051; this body requires code identification before tracing'
        result['ble_id_discrepancy']='Server name ble compared with observed runtime file 87; enum 89 is absent'
    if name in ('deadPixelsIndices','centers','bins','nPixelsPerBin'):
        result['table_layout_hypotheses']={str(w):{'whole_entries':len(body)//w,'remainder':len(body)%w} for w in (2,4,8)}
    return result


def inspect_response(raw, private, profiles):
    """Raw response must already be archived. Unknown names never become paths."""
    obj=json.loads(raw)
    if not isinstance(obj,dict) or 'new_version' not in obj:
        raise ValueError('unexpected response schema')
    offered=obj['new_version']
    if offered is None:
        return {'offer_state':'null','artifacts':[]}
    if not isinstance(offered,dict):
        raise ValueError('unexpected offer map')
    if not offered:
        return {'offer_state':'empty_map','artifacts':[]}
    artifacts=[]; errors=[]
    for index,(name,value) in enumerate(offered.items()):
        if name not in NAMES:
            # Preserve unknown entries without trusting the server's filename.
            r.write_new(inside_dev(private/f'quarantine_{index:02d}.json'),{'name':name,'value':value})
            errors.append('unknown firmware name quarantined')
            continue
        try:
            container=strict_container(value)
        except ValueError:
            errors.append('invalid known firmware container')
            continue
        save_bytes(private/f'{name}.container',container)
        save_bytes(private/f'{name}.prefix',container[:4])
        save_bytes(private/f'{name}.bin',container[4:])
        metadata=describe(name,container,profiles)
        metadata['private_body_path']=r.label(private/f'{name}.bin')
        artifacts.append(metadata)
    return {'offer_state':'offered','artifacts':artifacts,'validation_errors':errors}


def default_token():
    from scio import credentials
    with contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):
        token=credentials.get_token(prompt_if_needed=False,debug=False)
    if not isinstance(token,str) or not token:
        raise ValueError('authentication returned no token')
    return token


def run(out, contributor, *, live=False, token_provider=None, getter=None,
        monotonic=None, sleeper=None, max_response=MAX_RESPONSE):
    out=inside_dev(out)
    if out.exists():
        raise FileExistsError('new campaign directory required')
    jobs=jobs_for(contributor)
    plan={'schema':'scio-contributor-firmware-campaign/1','max_firmware_gets':4,
        'min_completion_gap_seconds':GAP,'client':CLIENT,'profiles':[OWN,contributor],
        'jobs':jobs,'auth':'Fresh token immediately before each GET; credentials read only',
        'source_code_sha256':r.sha(Path(__file__).read_bytes())}
    r.write_new(out/'plan.json',plan)
    if not live:
        return {'mode':'plan-only','firmware_gets':0}
    from scio import cloud
    token_provider=token_provider or default_token; getter=getter or requests.get
    monotonic=monotonic or time.monotonic; sleeper=sleeper or time.sleep
    private=inside_dev(r.DEV/'private'/'contributor_firmware'/(out.name+'_'+r.sha(r.label(out).encode())[:8]))
    private.mkdir(parents=True,exist_ok=False)
    rows=[]; completed=None
    for index,job in enumerate(jobs):
        if completed is not None:
            while monotonic()-completed<GAP:
                sleeper(GAP-(monotonic()-completed))
        profile=job['profile']
        params={'versions':json.dumps([{'key':k,'value':job['versions'][k]} for k in KEYS],separators=(',',':')),
                'compression_version':profile['i2s_tag_config']}
        row={'index':index,'name':job['name'],'profile_id':profile['profile_id'],
             'device_id':profile['device_id'],'ble_id':profile['ble_id'],
             'params':params,'client':CLIENT,'preparation_monotonic':monotonic()}
        r.write_new(out/f'{index:02d}_request.json',row)
        try:
            token=token_provider()
        except Exception as exc:
            row.update(halt_reason='authentication unavailable',exception_type=type(exc).__name__)
            rows.append(row);r.write_new(out/f'{index:02d}_result.json',row);break
        chunks=[]; size=0; truncated=False
        try:
            row['started_monotonic']=monotonic();row['started_unix']=time.time()
            with getter(cloud.API_BASE+'/device/'+profile['ble_id']+'/firmware-upgrade',params=params,
                headers={'Authorization':'Bearer '+token,'Accept':'application/json','X-SCiO-Client-Version':CLIENT},
                timeout=30,allow_redirects=False,stream=True) as response:
                row['status']=response.status_code
                for chunk in response.iter_content(65536):
                    room=max_response-size
                    if len(chunk)>room:
                        chunks.append(chunk[:room]);size+=room;truncated=True;break
                    chunks.append(chunk);size+=len(chunk)
            raw=b''.join(chunks)
            save_bytes(private/f'{index:02d}_response.bin',raw)
            row.update(response_sha256=r.sha(raw),response_bytes=len(raw),response_truncated=truncated,
                       private_response_path=r.label(private/f'{index:02d}_response.bin'))
            if truncated:
                row['halt_reason']='response size limit'
            elif row['status']!=200:
                row['halt_reason']='non-success HTTP status'
            else:
                row.update(inspect_response(raw,private/f'{index:02d}_files',[OWN,contributor]))
                if row.get('validation_errors'):
                    row['halt_reason']='malformed offered files'
        except Exception as exc:
            row.update(halt_reason='transport or response processing failure',exception_type=type(exc).__name__)
            if chunks and 'private_response_path' not in row:
                save_bytes(private/f'{index:02d}_partial_response.bin',b''.join(chunks))
        finally:
            token=None
        completed=monotonic();row['completed_monotonic']=completed
        r.write_new(out/f'{index:02d}_result.json',row);rows.append(row)
        print(job['name'],'HTTP',row.get('status'),'offer',row.get('offer_state'),'halt',row.get('halt_reason'),flush=True)
        if row.get('halt_reason') or row.get('offer_state')=='offered':
            break
    artifacts=[f for row in rows for f in row.get('artifacts',[])]
    summary={'rows':rows,'firmware_gets':sum('started_monotonic' in row for row in rows),
        'artifacts':artifacts,'validated_decoder':False,
        'limits':'Null bounds these exact account/device/versions/tag/client requests; encryption and checksum algorithm remain hypotheses'}
    if artifacts:
        bundle=private/'firmware_review.zip'
        with zipfile.ZipFile(bundle,'x',compression=zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(private.rglob('*')):
                if path.is_file() and path.suffix in ('.bin','.prefix','.container'):
                    archive.write(path,path.relative_to(private).as_posix())
        summary['private_review_bundle']={'path':r.label(bundle),'sha256':r.sha(bundle.read_bytes())}
    r.write_new(out/'artifact_manifest.json',{'artifacts':artifacts,'response_hashes':[row.get('response_sha256') for row in rows]})
    r.write_new(out/'summary.json',summary)
    return summary
