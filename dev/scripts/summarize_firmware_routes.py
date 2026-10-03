"""Cross-check bounded APK, server and USB outcomes without exposing raw strings."""
import argparse
import base64
from collections import Counter
import json
import re
from pathlib import Path
import _bootstrap
from scio_offline import research as r


def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    root=r.DEV/'analysis_output/recovery_20261003_followup'
    resource=json.loads((root/'embedded_resources_v2.json').read_text())
    dex=json.loads((root/'dex_arrays.json').read_text())
    server=json.loads((root/'firmware_server_recheck/summary.json').read_text())
    usb=json.loads((root/'usb_firmware_recheck.json').read_text())
    vendor=[x for x in dex['arrays'] if 'consumerphysics' in x['class']]
    non_resource=[x for x in vendor if '/R$' not in x['class']]
    lib=(r.DEV/'private/flutter_1_5_19_arm32/libapp.so').read_bytes()
    reviewed=[]
    for row in resource['candidate_leads']:
        item={'source':row['source'],'route':row['route'],'sha256':row['sha256'],'bytes':row['bytes']}
        if row['source'].endswith('.properties'):item['classification']='Properties resource; size-only match, no firmware evidence'
        elif '/__tzdata_' in row['source']:item['classification']='Named timezone resource; size-only match'
        elif '.png' in row['source']:item['classification']='Stream inside PNG resource; not SCIO-linked data'
        elif '/fonts/' in row['source']:item['classification']='Run inside font resource; size-only match, no SCIO payload linkage'
        elif 'libc++_shared.so' in row['source']:item['classification']='Run inside C++ runtime; size-only match, no SCIO payload linkage'
        else:item['classification']='Unvalidated Base64-compatible ASCII run; size-only match'
        if row['source'].endswith('libapp.so') and '1.5.19' in row['source']:
            offset=int(row['route'].split('@')[1]);match=re.match(rb'[A-Za-z0-9+/]+={0,2}',lib[offset:])
            token=match.group();data=base64.b64decode(token+b'='*(-len(token)%4),validate=True)
            if r.sha(data)!=row['sha256']:raise ValueError('candidate mismatch')
            item['input_bytes']=len(token)
            item['input_is_ascii_identifier']=token.decode().isidentifier()
            item['input_is_hex_digits']=bool(re.fullmatch(rb'[0-9a-fA-F]+',token))
        reviewed.append(item)
    timestamps=[x['started_unix'] for x in server['results']]
    r.write_new(a.output,{'resources':resource['counts'],'size_only_leads_reviewed':reviewed,
        'dex':{'files':len(dex['dex_files']),'array_candidates':len(dex['arrays']),
            'vendor_candidates':len(vendor),'vendor_non_R_candidates':non_resource,
            'structural_ldr_candidates':sum(bool(x['ldr_prefix_offsets']) for x in dex['arrays'])},
        'server':{'statuses':[x['status'] for x in server['results']],
            'null_offers':[x['new_version_is_null'] for x in server['results']],
            'wall_clock_start_gaps_seconds':[b-a for a,b in zip(timestamps,timestamps[1:])],
            'timing_note':'Run used a monotonic 20-second start-based scheduler. Wall-clock timestamps include bookkeeping/clock jitter. Future runner now waits 20 seconds after completion.'},
        'usb':{'device':usb['device'],'read_errors':[x for x in usb['queries'] if 'error_type' in x],
            'captures':len(usb['captures']),'body_read_command_established':False},
        'outcome':'No validated firmware/table body or offline spectrum decoder recovered. No updates/reset/speculative USB writes. APK/code coverage bounded; device headers and null server offers do not establish global unavailability.'})
    print('Vendor non-resource candidates',len(non_resource),'resource leads',len(reviewed))


if __name__=='__main__':main()
