"""Bounded exact-match MAC hypotheses; no inference from mere server rejection."""
import argparse
import hashlib
import hmac
from pathlib import Path
from cryptography.hazmat.primitives import cmac
from cryptography.hazmat.primitives.ciphers import algorithms
import _bootstrap
from scio import session
from scio_offline import research as r, search_v2


def value(key,algorithm,data):
    if algorithm=='AES-CMAC':
        c=cmac.CMAC(algorithms.AES(key)); c.update(data); return c.finalize()
    return hmac.new(key,data,algorithm).digest()


def split(blob,field,coverage,identity):
    if field=='header_word2': expected=blob[4:8]; body=blob[8:]; prefix=blob[:4]
    else: expected=blob[-16:]; body=blob[8:-16]; prefix=blob[:8]
    return expected,{'body':body,'header_body':prefix+body,'identity_body':identity.encode()+body}[coverage]


def main():
    p=argparse.ArgumentParser(); p.add_argument('--output',required=True); a=p.parse_args()
    groups={}
    for path in sorted(Path('01_rawdata/scans').glob('*.json')):
        rec=session.load_record(path); d=rec['device']; identity=(d['device_id'],d['i2s_tag_config'])
        g=groups.setdefault(identity,{'metadata':{},'blobs':{}})
        for source in (d,d.get('device_info_raw') or {}):
            for k,v in source.items():
                if v is not None and v!='' and not isinstance(v,dict): g['metadata'].setdefault(k,v)
        s,w=session.record_blobs(rec)
        for blob in {**s,**w}.values():g['blobs'][r.sha(blob)]=blob
    results=[]
    for identity,g in groups.items():
        keys=search_v2.candidate_keys(g['metadata'],True); blobs=list(g['blobs'].values()); matches=[]; attempted=0
        configs=[(field,coverage,algorithm,end) for field in ('header_word2','tail16') for coverage in ('body','header_body','identity_body') for algorithm in ('md5','sha1','sha256','AES-CMAC') for end in ('first','last')]
        for key in keys:
            for field,coverage,algorithm,end in configs:
                attempted+=1; expected,data=split(blobs[0],field,coverage,identity[0]); digest=value(key,algorithm,data)
                actual=digest[:len(expected)] if end=='first' else digest[-len(expected):]
                if actual!=expected: continue
                passed=[]
                for blob in blobs[1:]:
                    expect,data=split(blob,field,coverage,identity[0]); digest=value(key,algorithm,data)
                    actual=digest[:len(expect)] if end=='first' else digest[-len(expect):]
                    passed.append(actual==expect)
                matches.append({'key_sha256':r.sha(key),'config':[field,coverage,algorithm,end],
                                'independent_matches':sum(passed),'confirmed':bool(passed) and all(passed)})
        results.append({'device_id':identity[0],'i2s_tag':identity[1],'configurations':configs,'unique_keys':len(keys),
                        'attempted':attempted,'blob_sha256':list(g['blobs']),'screen_matches':matches})
    r.write_new(a.output,{'groups':results,'limits':'First-record rejection bounds these exact key/field/coverage hypotheses only. No other MAC, checksum, key or envelope is excluded.'})
    print('MAC hypotheses tested',sum(g['attempted'] for g in results))


if __name__=='__main__':main()
