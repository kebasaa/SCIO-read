"""Recover SCIO frames from supplied historical phone logs, without device I/O."""
import argparse
import base64
import json
from collections import Counter
from pathlib import Path
import _bootstrap
from scio_offline import research as r
from scio_offline.snoop import extract


def main():
    p=argparse.ArgumentParser();p.add_argument('--apps',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    logs=[]
    manifest=json.loads((r.DEV/'analysis_output/recovery_20261003/corpus_final.json').read_text())
    # Compare against all serialized hashes, including foreign app fixtures.
    manifest_text=json.dumps(manifest)
    for path in sorted(a.apps.glob('btsnoop*')):
        raw=path.read_bytes(); parsed=extract(raw); commands=Counter()
        for message in parsed['messages']:
            commands[f"{message['direction']}/{message['command']:02x}"]+=1
            data=message.pop('data');message['bytes']=len(data);message['sha256']=r.sha(data)
            if message['command']==2 and message['direction']=='received':
                message['blob_b64']=base64.b64encode(data).decode()
                message['in_previous_manifest']=message['sha256'] in manifest_text
                message['identity']='Unestablished from this log; do not pool device-specific key candidates.'
            # Do not export device names or arbitrary payloads. Firmware transfers
            # are candidates only; metadata and blob content need separate review.
            if message['command']==0x81 and message['direction']=='sent': message['firmware_candidate_hex']=data.hex()
            if message['command']==0x84 and message['direction']=='received':
                field=data[66:130]
                message['i2s_field_hex']=field.hex()
                message['i2s_field_all_zero']=bool(field) and not any(field)
        logs.append({'source':path.name,'sha256':r.sha(raw),**parsed,'command_counts':dict(commands)})
    r.write_new(a.output,{'logs':logs,'limits':'Only complete framed SCIO messages are exported. No firmware identification from a marker alone. Missing transfers in these finite logs do not exclude phone caches or other logs.'})
    for log in logs: print(log['source'],log['counts'],log['command_counts'])


if __name__=='__main__':main()
