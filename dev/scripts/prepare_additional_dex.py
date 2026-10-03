"""Inventory exact follow-up APK contents and extract DEX only, under dev."""
import argparse
import io
import zipfile
import _bootstrap
from pathlib import Path
from audit_dex_boundary import dex_members
from scio_offline import research as r


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--apps',type=Path,required=True)
    p.add_argument('--target',choices=['analyzer_1_5_19','lab_1_3_12'],required=True)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    name={'analyzer_1_5_19':'SCiO+Analyzer_1.5.19_APKPure.xapk',
          'lab_1_3_12':'The Lab Dev Toolkit for SCiO_1.3.12.144_Apkpure.apk'}[a.target]
    raw=(a.apps/'apk'/name).read_bytes()
    directory=r.DEV/'private'/f'{a.target}_dex'
    directory.mkdir(parents=True,exist_ok=True)
    rows=[]
    for i,(origin,data) in enumerate(dex_members(raw,name)):
        path=directory/f'input_{i}.dex'
        if path.exists():
            if path.read_bytes()!=data: raise ValueError('existing input differs')
        else:
            with path.open('xb') as f: f.write(data)
        rows.append({'source':origin,'sha256':r.sha(data),'bytes':len(data),'path':r.label(path),
            'diagnostic_labels_present':[s for s in ['sample_gradient_chars','sample_gradient_decoded_bytes','sample_gradient_preview'] if s.encode() in data]})
    entries=[]
    def inventory(data,origin):
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            for item in z.infolist():
                if item.is_dir(): continue
                member=z.read(item)
                entries.append({'source':origin+'!'+item.filename,'bytes':len(member),'sha256':r.sha(member)})
                if item.filename.endswith('.apk'): inventory(member,origin+'!'+item.filename)
    inventory(raw,name)
    r.write_new(a.output,{'source':name,'sha256':r.sha(raw),'dex':rows,'members':entries,
        'limits':'Content inventory and DEX extraction, not semantic coverage.'})
    print('DEX count',len(rows),'archive members',len(entries))


if __name__=='__main__': main()
