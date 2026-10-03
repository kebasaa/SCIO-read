"""Unknown-polynomial CRC recovery, separated by device, generation and role."""
import argparse
import base64
import json
from pathlib import Path
import _bootstrap
from scio import session
from scio_offline import research as r,crc_recovery


def main():
    p=argparse.ArgumentParser(); p.add_argument('--output',required=True); a=p.parse_args(); groups={}
    def add(device,tag,blobs):
        for role,b in blobs.items(): groups.setdefault((device,tag,role,len(b)),{})[r.sha(b)]=b
    for path in sorted(Path('01_rawdata/scans').glob('*.json')):
        rec=session.load_record(path); s,w=session.record_blobs(rec); d=rec['device']
        add(d['device_id'],d['i2s_tag_config'],{**s,**w})
    for path in sorted(Path('dev/analysis_output/foreign_scans').glob('*.json')):
        rec=json.loads(path.read_text()); add(rec['device_id'],rec['i2s_tag_config'],{k:base64.b64decode(v) for k,v in rec.get('blobs_b64',{}).items()})
    rows=[]
    for identity,blobs in groups.items():
        result=crc_recovery.recover(list(blobs.values())) if len(blobs)>=4 else {'skipped':'fewer than four independent blobs','records':len(blobs)}
        rows.append({'identity':identity,'blob_sha256':list(blobs),**result})
        print(identity[2],len(blobs),'candidates',len(result.get('hits',[])),flush=True)
    r.write_new(a.output,{'groups':rows,'cipher_assumed':False})


if __name__=='__main__':main()
