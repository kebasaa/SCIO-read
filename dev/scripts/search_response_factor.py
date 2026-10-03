"""Bounded exact numeric-table search tied to the observed self-response factor."""
import argparse
import io
import json
import struct
import zipfile
from pathlib import Path
import _bootstrap
from scio_offline import research as r


def members(raw,origin):
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        for name in z.namelist():
            if name.endswith('/'):continue
            b=z.read(name)
            if name.endswith('.apk'):yield from members(b,origin+'!'+name)
            else:yield origin+'!'+name,b


def main():
    p=argparse.ArgumentParser();p.add_argument('--apps',type=Path,required=True);p.add_argument('--factor',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    factor=json.loads(a.factor.read_text());patterns=[]
    for transform in ('factor','inverse_factor'):
        for endian in ('<','>'):
            for kind in ('f','d'):
                for start in (0,100,200,327):
                    patterns.append(({'transform':transform,'endian':endian,'type':kind,'band_index':start},struct.pack(endian+kind*4,*factor[transform][start:start+4])))
    count=0;size=0;hits=[];archives=[]
    for path in sorted((a.apps/'apk').iterdir()):
        if path.suffix not in ('.apk','.xapk'):continue
        raw=path.read_bytes();archives.append({'name':path.name,'sha256':r.sha(raw)})
        for name,data in members(raw,path.name):
            count+=1;size+=len(data)
            for description,needle in patterns:
                offset=data.find(needle)
                if offset>=0:hits.append({'source':name,'sha256':r.sha(data),'offset':offset,**description})
    r.write_new(a.output,{'archives':archives,'factor_source':r.label(a.factor),'factor_sha256':r.sha(a.factor.read_bytes()),
        'member_count':count,'uncompressed_bytes_checked':size,'patterns':len(patterns),'hits':hits,
        'limits':'Exact four-value anchors, float32/float64, both endian orders, C and 1/C. Does not exclude generated/polynomial, quantized, interleaved, encoded or compressed tables.'})
    print('members',count,'patterns',len(patterns),'hits',len(hits))


if __name__=='__main__':main()
