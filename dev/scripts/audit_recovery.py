"""Read-only evidence inventory; all reports are immutable and below dev."""
import argparse
import hashlib
import io
import json
import re
import zipfile
import zlib
from pathlib import Path
import _bootstrap
from scio_offline import research as r


def archive(raw, name):
    members=[]
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        for entry in z.infolist():
            if entry.is_dir(): continue
            b=z.read(entry)
            row={'name':entry.filename,'bytes':len(b),'sha256':r.sha(b)}
            if entry.filename.endswith('.apk'):
                row['members']=archive(b,entry.filename)
            if entry.filename.endswith(('.dex','.so')):
                strings=re.findall(rb'[ -~]{6,}',b)
                pattern=re.compile(rb'spectro.scan|dsp_boot|dsp_op|dsp_dec|firmware.upgrade|compression_version|Bad_sample_signature|sample_gradient|i2s_tag',re.I)
                row['path_strings']=sorted({s.decode('ascii')[:300] for s in strings if pattern.search(s)})
                row['coverage']='printable strings only; not complete control-flow analysis'
            members.append(row)
    return members


def apps(root):
    archives=[]; sources=[]; hits=[]
    patterns=re.compile(r'FirmwareUpgradeModel|spectro-scan|compression_version|dsp_boot|dsp_dec|Base64\.decode|sample_gradient|Bad_sample_signature')
    for p in sorted(root.rglob('*')):
        if not p.is_file(): continue
        relative=p.relative_to(root).as_posix()
        if p.parent.name=='apk' and p.suffix.lower() in ('.apk','.xapk'):
            b=p.read_bytes(); archives.append({'name':p.name,'sha256':r.sha(b),'bytes':len(b),'members':archive(b,p.name)})
        elif p.suffix in ('.java','.kt','.dart'):
            b=p.read_bytes(); sources.append({'path':relative,'sha256':r.sha(b),'bytes':len(b)})
            # Restrict excerpts to vendor code; third-party crypto is not a payload key.
            if 'consumerphysics' in relative.lower():
                for n,line in enumerate(b.decode('utf-8',errors='replace').splitlines(),1):
                    if patterns.search(line): hits.append({'path':relative,'line':n,'text':line.strip()[:300]})
    return {'archives':archives,'source_files':sources,'vendor_path_references':hits,
            'limits':'Archive members and source files hashed. String references are leads, not recovered keys or validated firmware. Flutter control flow and exhaustive encoded-array search remain incomplete.'}


def integrity(rows):
    records={r.sha(b):(role,b,d['device'].get('device_id','')) for d in rows for role,b in d['blobs'].items()}
    counts={}; matches={}
    for digest,(role,b,identity) in records.items():
        for field,expected,body in [('word2',b[4:8],b[8:]),('tail4',b[-4:],b[8:-4])]:
            for coverage,data in [('body',body),('status_body',b[:4]+body),('identity_body',identity.encode()+body)]:
                funcs={'crc32':zlib.crc32(data)&0xffffffff,'adler32':zlib.adler32(data)&0xffffffff,'sum8':sum(data)&0xffffffff}
                for alg,value in funcs.items():
                    for endian in ('little','big'):
                        key=f'{field}/{coverage}/{alg}/{endian}'
                        counts[key]=counts.get(key,0)+1
                        if value.to_bytes(4,endian)==expected: matches.setdefault(key,[]).append(digest)
                for alg in ('md5','sha1','sha256'):
                    h=hashlib.new(alg,data).digest()
                    for end,value in [('first4',h[:4]),('last4',h[-4:])]:
                        key=f'{field}/{coverage}/{alg}/{end}'; counts[key]=counts.get(key,0)+1
                        if value==expected: matches.setdefault(key,[]).append(digest)
    return {'unique_blobs':len(records),'tested':counts,'matches':matches,
            'limits':'Bounded unkeyed 32-bit fields only. No MAC or other integrity mechanism excluded.'}


def main():
    p=argparse.ArgumentParser(); p.add_argument('--output',required=True); p.add_argument('--apps',type=Path,required=True)
    a=p.parse_args(); out=Path(a.output)
    if not (out/'input_snapshot.json').exists():
        r.write_new(out/'input_snapshot.json',r.snapshot())
    r.write_new(out/'corpus.json',r.manifest())
    r.write_new(out/'integrity.json',integrity(r.contexts()))
    r.write_new(out/'apps.json',apps(a.apps))
    print('Audit complete',flush=True)


if __name__=='__main__': main()
