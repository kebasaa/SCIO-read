"""Run bounded keyless codec probes on all canonical/foreign opaque bodies."""
import argparse
import base64
import json
from pathlib import Path
import numpy as np
import _bootstrap
from scio import session
from scio_offline import research as r
from scio_offline.compression_only import probe,FACTORIES


def main():
    p=argparse.ArgumentParser(); p.add_argument('--output',required=True); a=p.parse_args()
    blobs={}
    for path in sorted(Path('01_rawdata/scans').glob('*.json')):
        rec=session.load_record(path); s,w=session.record_blobs(rec)
        for role,b in {**s,**w}.items():
            blobs.setdefault(r.sha(b),{'blob':b,'occurrences':[]})['occurrences'].append({'role':role,'device_id':rec['device']['device_id'],'i2s_tag':rec['device']['i2s_tag_config']})
    for path in sorted(Path('dev/analysis_output/foreign_scans').glob('*.json')):
        rec=json.loads(path.read_text())
        for role,text in rec.get('blobs_b64',{}).items():
            b=base64.b64decode(text)
            blobs.setdefault(r.sha(b),{'blob':b,'occurrences':[]})['occurrences'].append({'role':role,'device_id':rec['device_id'],'i2s_tag':rec['i2s_tag_config']})
    rows=[]
    for i,(h,b) in enumerate(blobs.items()):
        rows.append({'blob_sha256':h,'occurrences':b['occurrences'],'hits':probe(b['blob'][8:])})
        if i%50==0: print('keyless blobs',i+1,'/',len(blobs),flush=True)
    rng=np.random.default_rng(197); controls=[probe(rng.bytes(1792)) for _ in range(32)]
    r.write_new(a.output,{'cipher_step':None,'keys_used':0,'unique_blobs':len(rows),'codecs':list(FACTORIES),
        'byte_offsets':list(range(33)),'bit_offsets':list(range(8)),
        'configurations_per_blob':33*8*len(FACTORIES),'observations':rows,'random_controls':controls,
        'limits':'Completed or partial streams are leads, not spectra. Random controls measure accidental parses. Misses bound only these codecs, offsets and memory/output limits; proprietary/headerless image, Rice, Huffman, arithmetic, DCT/wavelet, predictive and table-driven compression remain possible without encryption.'})
    print('keyless compression scan complete',flush=True)


if __name__=='__main__':main()
