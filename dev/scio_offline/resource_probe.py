"""Bounded static decoding helpers. No app execution or inferred firmware identity."""
import base64
import bz2
import json
import lzma
import re
import zlib

MAX_OUTPUT=8*1024*1024


def decompress(data,kind,limit=MAX_OUTPUT):
    if kind in ('gzip','zlib'):
        obj=zlib.decompressobj(31 if kind=='gzip' else 15)
        out=obj.decompress(data,limit+1)
        complete=obj.eof and not obj.unconsumed_tail
    elif kind=='bzip2':
        obj=bz2.BZ2Decompressor();out=obj.decompress(data,max_length=limit+1);complete=obj.eof
    elif kind=='xz':
        obj=lzma.LZMADecompressor(memlimit=64*1024*1024);out=obj.decompress(data,max_length=limit+1);complete=obj.eof
    else:raise ValueError('unsupported codec')
    if len(out)>limit or not complete:raise ValueError('incomplete or oversized stream')
    return out,len(data)-len(obj.unused_data)


def encoded_runs(data):
    # Contiguous runs only: cover binary strings/DEX without assuming DEX encoding.
    for match in re.finditer(rb'(?<![A-Za-z0-9+/])[A-Za-z0-9+/]{128,}={0,2}',data):
        value=match.group()
        if len(value)>MAX_OUTPUT*2:continue
        try:decoded=base64.b64decode(value+b'='*(-len(value)%4),validate=True)
        except ValueError:continue
        yield match.start(),'base64-run',decoded
    for match in re.finditer(rb'(?<![0-9A-Fa-f])[0-9A-Fa-f]{128,}(?![0-9A-Fa-f])',data):
        value=match.group()
        if len(value)%2==0 and len(value)<=MAX_OUTPUT*2:
            yield match.start(),'hex-run',bytes.fromhex(value.decode('ascii'))


def java_constants(text):
    for match in re.finditer(r'"(?:[^"\\\r\n]|\\.){128,}"',text):
        try:value=json.loads(match.group())
        except ValueError:continue
        compact=''.join(value.split())
        if len(compact)>MAX_OUTPUT*2:continue
        try:decoded=base64.b64decode(compact+'='*(-len(compact)%4),validate=True)
        except (ValueError,UnicodeEncodeError):continue
        yield match.start(),'java-base64-string',decoded
    pattern=r'new\s+(byte|short|int)\s*\[\s*\]\s*\{([^{}]{64,})\}'
    for match in re.finditer(pattern,text):
        width={'byte':1,'short':2,'int':4}[match[1]]
        pieces=match[2].split(',');values=[]
        if len(pieces)>MAX_OUTPUT//width:continue
        for piece in pieces:
            piece=re.sub(r'\((byte|short|int)\)','',piece).strip()
            if not re.fullmatch(r'-?(?:0[xX][0-9a-fA-F]+|\d+)',piece):break
            number=int(piece,16 if 'x' in piece.lower() else 10)
            if not -(1<<(width*8-1))<=number<(1<<(width*8)):break
            values.append(number&((1<<(width*8))-1))
        else:
            if len(values)*width>=64:
                for order in (('little',) if width==1 else ('little','big')):
                    yield match.start(),'java-'+match[1]+'-'+order,b''.join(v.to_bytes(width,order) for v in values)


def formats(data):
    signatures=((b'\x7fELF','ELF'),(b'dex\n','DEX'),(b'\x89PNG','PNG'),
        (b'\xff\xd8\xff','JPEG'),(b'PK\x03\x04','ZIP'),(b'wOFF','WOFF'),(b'OTTO','OTF'),
        (b'\x00\x01\x00\x00','TTF-candidate'))
    return next((kind for prefix,kind in signatures if data.startswith(prefix)),None)
