"""Bounded asset triage independent of firmware size; archive inputs are read-only."""
import argparse
import base64
import io
import re
import struct
import zipfile
from pathlib import Path
import _bootstrap
from scio_offline import research as r


def walk(raw, origin, findings, embedded):
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        for name in z.namelist():
            if name.endswith('/'): continue
            if name.endswith('.apk'):
                walk(z.read(name),origin+'!'+name,findings,embedded); continue
            relevant=bool(re.search(r'^assets/|\.bin$|\.dat$|\.so$',name))
            if not relevant or re.search(r'\.(png|jpg|webp|mp4|ttf|otf|svg|woff2?)$',name,re.I): continue
            b=z.read(name); item={'archive':origin,'member':name,'sha256':r.sha(b),'bytes':len(b)}
            if b.startswith(b'\x7fELF'):
                item['format']='ELF'; item['elf_class']=b[4]; item['machine']=int.from_bytes(b[18:20],'little' if b[5]==1 else 'big')
            elif b.startswith(b'\x1f\x8b'): item['format']='gzip'
            elif b.startswith(b'PK\x03\x04'): item['format']='zip'
            else: item['format']='unclassified asset'
            if '/mock/' in name:
                try:
                    decoded=base64.b64decode(b''.join(b.split()),validate=True)
                    item['decoded_sha256']=r.sha(decoded); item['decoded_bytes']=len(decoded)
                    embedded.append({**item,'blob_b64':base64.b64encode(decoded).decode(),
                        'association':'Asset path only; device identity not inferred from bytes.'})
                except ValueError: item['base64_valid']=False
            findings.append(item)


def main():
    p=argparse.ArgumentParser(); p.add_argument('--apps',type=Path,required=True); p.add_argument('--output',type=Path,required=True); a=p.parse_args()
    findings=[]; embedded=[]
    for path in sorted((a.apps/'apk').iterdir()):
        if path.suffix in ('.apk','.xapk'): walk(path.read_bytes(),path.name,findings,embedded)
    r.write_new(a.output,{'assets':findings,'embedded_samples':embedded,
        'limits':'Name-independent asset inventory excluding visual/font extensions. Does not exhaust encoded arrays in code or custom containers. ELF recognition is not SCIO firmware validation.'})
    print('asset candidates',len(findings),'embedded sample occurrences',len(embedded))


if __name__=='__main__': main()
