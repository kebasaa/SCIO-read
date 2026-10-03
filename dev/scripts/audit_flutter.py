"""Inspect supplied Flutter ELF snapshots without downloading reverse-engineering tools."""
import argparse
import io
import re
import struct
import zipfile
from pathlib import Path
import _bootstrap
from scio_offline import research as r


def elf_sections(raw):
    if raw[:6] not in (b'\x7fELF\x01\x01',b'\x7fELF\x02\x01'): raise ValueError('unsupported ELF')
    is64=raw[4]==2
    off=struct.unpack_from('<Q' if is64 else '<I',raw,40 if is64 else 32)[0]
    size,count,names=struct.unpack_from('<HHH',raw,58 if is64 else 46)
    fmt='<IIQQQQIIQQ' if is64 else '<IIIIIIIIII'
    table=[struct.unpack_from(fmt,raw,off+i*size) for i in range(count)]
    ns=table[names]; strings=raw[ns[4]:ns[4]+ns[5]]
    sections=[]
    for row in table:
        start=row[0];end=strings.find(b'\0',start)
        sections.append({'name':strings[start:end].decode('ascii'),'type':row[1],'address':row[3],
            'offset':row[4],'size':row[5],'link':row[6],'entry_size':row[9]})
    symbols=[]
    for sec in sections:
        if sec['type'] not in (2,11) or not sec['entry_size']: continue
        linked=sections[sec['link']]; strings=raw[linked['offset']:linked['offset']+linked['size']]
        for off in range(sec['offset'],sec['offset']+sec['size'],sec['entry_size']):
            start=struct.unpack_from('<I',raw,off)[0];end=strings.find(b'\0',start)
            name=strings[start:end].decode('ascii',errors='replace')
            if is64: value,n=struct.unpack_from('<QQ',raw,off+8)
            else: value,n=struct.unpack_from('<II',raw,off+4)
            if name: symbols.append({'name':name,'value':value,'size':n})
    return sections,symbols


def members(raw,origin):
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        for name in z.namelist():
            if name.endswith('.apk'): yield from members(z.read(name),origin+'!'+name)
            elif name.endswith('/libapp.so'): yield origin+'!'+name,z.read(name)


def main():
    p=argparse.ArgumentParser();p.add_argument('--apps',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    findings=[]
    pattern=re.compile(rb'firmware|spectro|i2s|compress|decrypt|encrypt|checksum|sample_gradient|sample_white|dead.pixel|nPixels|dsp_boot|dsp_dec|dsp_op|jpeg|huffman|rice|golomb',re.I)
    for path in sorted((a.apps/'apk').iterdir()):
        if path.suffix not in ('.apk','.xapk'): continue
        for origin,raw in members(path.read_bytes(),path.name):
            sections,symbols=elf_sections(raw); strings=[]
            for match in re.finditer(rb'[ -~]{5,}',raw):
                value=match.group()
                if not pattern.search(value) or len(value)>350: continue
                # Avoid exporting arbitrary string values or build-machine paths.
                if b':\\' in value or b'/Users/' in value or b'/home/' in value: continue
                strings.append({'offset':match.start(),'text':value.decode('ascii')})
            findings.append({'source':origin,'sha256':r.sha(raw),'bytes':len(raw),
                'sections':sections,'symbols':symbols,'relevant_strings':strings})
    r.write_new(a.output,{'libraries':findings,'limits':'ELF sections, exported symbols and located strings, not recovered Dart object-pool references or control-flow. Generic crypto/codec names do not establish payload use.'})
    for x in findings: print(x['source'],len(x['symbols']),'symbols',len(x['relevant_strings']),'relevant strings')


if __name__=='__main__':main()
