"""Preserve APK mock provenance without treating mock IDs as real identities."""
import argparse
import base64
import json
import re
import struct
import zipfile
from pathlib import Path
import _bootstrap
from scio_offline import research as r


def mock_constants(text):
    """Allowlisted Java string literals only; never evaluate Java source."""
    pattern=r'public static final String (SAMPLE(?:_DARK|_GRADIENT)?|WR(?:_DARK|_GRADIENT)?) = ("(?:[^"\\]|\\.)*");'
    return {name:base64.b64decode(''.join(json.loads(value).split()),validate=True)
            for name,value in re.findall(pattern,text)}


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--apk',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    prior=json.loads((r.DEV/'analysis_output/recovery_20261003/assets.json').read_text())
    known={x['decoded_sha256'] for x in prior['embedded_samples']}
    rows=[]
    directory=r.DEV/'private/lab_1_3_12_fixtures'
    directory.mkdir(parents=True,exist_ok=True)
    def add(origin,value,name):
        data=base64.b64decode(b''.join(value.split()),validate=True)
        path=directory/(name+'.bin')
        if path.exists():
            if path.read_bytes()!=data: raise ValueError('fixture changed')
        else:
            with path.open('xb') as f:f.write(data)
        rows.append({'source':origin,'sha256':r.sha(data),'bytes':len(data),
            'header_u32le':list(struct.unpack_from('<II',data)),
            'in_prior_asset_inventory':r.sha(data) in known,'private_path':r.label(path)})
    with zipfile.ZipFile(a.apk) as z:
        for name in z.namelist():
            if name.startswith('assets/mock/') and not name.endswith('/'):
                add(a.apk.name+'!'+name,z.read(name),'asset_'+Path(name).name)
        native=[name for name in z.namelist() if name.endswith('.so')]
    source=r.DEV/'private/lab_1_3_12_java/sources/com/consumerphysics/researcher/mock/MockSamples.java'
    text=source.read_text()
    for name,value in re.findall(r'public static final String (SAMPLE(?:_DARK|_GRADIENT)?|WR(?:_DARK|_GRADIENT)?) = ("(?:[^"\\]|\\.)*");',text):
        add('MockSamples.java:'+name,json.loads(value).encode(),'constant_'+name)
    r.write_new(a.output,{'apk_sha256':r.sha(a.apk.read_bytes()),'fixtures':rows,
        'mock_source_sha256':r.sha(source.read_bytes()),'native_libraries':native,
        'unique_blobs':len({x['sha256'] for x in rows}),
        'limits':'Mock-associated blobs, not paired spectral truth. Class-level placeholder IDs/i2s are not validated capture identities. Prior asset membership does not check all older code fixtures.'})
    print('fixture occurrences',len(rows),'unique',len({x['sha256'] for x in rows}),'native libraries',len(native))


if __name__=='__main__':main()
