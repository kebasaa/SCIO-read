"""Inspect array payload candidates within actual DEX code_items, not Java output."""
import argparse
import struct
from pathlib import Path
import _bootstrap
from audit_dex_boundary import uleb,dex_members,definitions
from scio_offline import research as r
from scio_offline.firmware import parse_ldr


def arrays(raw):
    names=definitions(raw)
    classes_n,classes_off=struct.unpack_from('<II',raw,96)
    for index in range(classes_n):
        pos=struct.unpack_from('<I',raw,classes_off+index*32+24)[0]
        if not pos:continue
        counts=[]
        for _ in range(4):value,pos=uleb(raw,pos);counts.append(value)
        for _ in range(counts[0]+counts[1]):
            _,pos=uleb(raw,pos);_,pos=uleb(raw,pos)
        for count in counts[2:]:
            method=0
            for _ in range(count):
                delta,pos=uleb(raw,pos);method+=delta
                _,pos=uleb(raw,pos);code,pos=uleb(raw,pos)
                if not code:continue
                if code%4 or code+16>len(raw):raise ValueError('invalid code_item')
                length=struct.unpack_from('<I',raw,code+12)[0]*2
                start,end=code+16,code+16+length
                if end>len(raw):raise ValueError('instructions outside file')
                seen=set()
                # Candidate references: no complete Dalvik opcode-boundary decoder.
                for at in range(start,end-5,2):
                    if raw[at]!=0x26:continue
                    target=at+2*struct.unpack_from('<i',raw,at+2)[0]
                    if target in seen or target%4 or not start<=target<=end-8:continue
                    if raw[target:target+2]!=b'\0\x03':continue
                    width,n=struct.unpack_from('<HI',raw,target+2)
                    if width not in (1,2,4,8) or n*width<64 or target+8+n*width>end:continue
                    seen.add(target)
                    yield {'class':names[index],'method_index':method,'code_offset':code,
                        'reference_offset':at,'payload_offset':target,'element_width':width,'elements':n},raw[target+8:target+8+n*width]


def main():
    p=argparse.ArgumentParser();p.add_argument('--apps',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    seen=set();rows=[];files=[]
    private=r.DEV/'private/dex_array_candidates';private.mkdir(parents=True,exist_ok=True)
    for path in sorted((a.apps/'apk').iterdir()):
        if path.suffix.lower() not in ('.apk','.xapk'):continue
        for origin,raw in dex_members(path.read_bytes(),path.name):
            digest=r.sha(raw)
            if digest in seen:continue
            seen.add(digest);before=len(rows)
            for row,data in arrays(raw):
                ldr=[off for off in (0,4,8,16) if len(data)>=off+16 and data[off+3]==0xad and parse_ldr(data[off:])['valid_ldr']]
                record={**row,'source':origin,'bytes':len(data),'sha256':r.sha(data),'ldr_prefix_offsets':ldr}
                rows.append(record)
                if ldr or ('consumerphysics' in row['class'] and len(data)>=1024):
                    output=private/(r.sha(data)+'.bin')
                    if not output.exists():
                        with output.open('xb') as f:f.write(data)
            files.append({'source':origin,'sha256':digest,'array_candidates':len(rows)-before})
    r.write_new(a.output,{'dex_files':files,'arrays':rows,'limits':'Code_item-bounded syntactic fill-array-data reference candidates, not full instruction-boundary/control-flow decoding. Literal payloads >=64 bytes only; no computed/decrypted arrays or array element assignments. Structural LDR matches at prefixes 0/4/8/16 are leads, not firmware verification.'})
    print('DEX files',len(files),'array candidates',len(rows),'vendor arrays',sum('consumerphysics' in x['class'] for x in rows),'LDR candidates',sum(bool(x['ldr_prefix_offsets']) for x in rows))


if __name__=='__main__':main()
