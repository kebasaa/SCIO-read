"""Read only the first canonical RO-string allocation cluster; fail closed."""
import struct
import json
import hashlib
from pathlib import Path
import _bootstrap
from scio_offline import research as r


def read_var(raw, pos, marker=128):
    result = 0
    for shift in range(0, 35, 7):
        if pos >= len(raw):
            raise ValueError('truncated variable integer')
        byte = raw[pos]
        pos += 1
        if byte >= 128:
            return result | ((byte-marker) << shift), pos
        result |= byte << shift
    raise ValueError('oversized variable integer')


def encode_ref(value):
    if not 0 <= value < 1 << 28:
        raise ValueError('reference outside supported range')
    parts = [value & 127]
    while value > 127:
        value >>= 7
        parts.append(value & 127)
    parts.reverse()
    parts[-1] |= 128
    return bytes(parts)


def encode_unsigned(value):
    if not 0 <= value < 1 << 32:
        raise ValueError('unsigned outside supported range')
    parts = []
    while value > 127:
        parts.append(value & 127)
        value >>= 7
    return bytes(parts+[value+128])


def read_ref(raw,pos):
    value = 0
    for _ in range(4):
        if pos >= len(raw):
            raise ValueError('truncated reference')
        b = raw[pos]
        pos += 1
        value = (value << 7) | (b & 127)
        if b >= 128:
            return value,pos
    raise ValueError('reference overflow')


def pool_entries(raw,pos,count,maxref):
    rows = []
    for index in range(count):
        if pos >= len(raw):
            raise ValueError('truncated pool')
        bits = raw[pos]
        pos += 1
        kind,behavior = bits&15,bits>>5
        value = None
        if kind > 2:
            raise ValueError('invalid entry type')
        if behavior in (2,3,4):
            pass
        elif behavior != 0:
            raise ValueError('invalid entry bits')
        elif kind == 1:
            value,pos = read_ref(raw,pos)
            if value > maxref:
                raise ValueError('reference outside snapshot')
        elif kind == 0:
            _,pos = read_var(raw,pos,192)
        rows.append(value)
    return rows,pos


def main():
    raw = (r.DEV/'private/flutter_1_5_19_arm32/libapp.so').read_bytes()
    if hashlib.sha256(raw).hexdigest() != '9d46ae6000a652971848fecb894402727183ca07c986762198283564d9aecd9c':
        raise ValueError('unsupported binary; this probe is target-specific')
    start = 30080  # Exact ELF-exported isolate data offset, verified in manifest.
    pos = raw.index(b'\0', start+52)+1
    values = []
    for _ in range(5):
        value, pos = read_var(raw,pos)
        values.append(value)
    tags, pos = read_var(raw,pos,192)
    count, pos = read_var(raw,pos)
    print('header',values,'first cluster tags',hex(tags),'cid',tags>>12,'count',count,'offset',hex(pos))
    cumulative = 0
    offsets = []
    for _ in range(count):
        delta,pos = read_var(raw,pos)
        cumulative += delta*8
        offsets.append(cumulative)
    print('allocation end',hex(pos),'offset range',hex(offsets[0]),hex(offsets[-1]))
    n = struct.unpack_from('<Q',raw,start+4)[0]
    image = start+((n+4+63)&~63)
    strings = {}
    for i,offset in enumerate(offsets):
        obj = image+offset
        tag, _, size = struct.unpack_from('<III',raw,obj)
        if tag >> 12 not in (94,95) or size & 1:
            raise ValueError('not an aligned string object')
        length = size >> 1
        if tag >> 12 == 94:
            strings[values[0]+1+i] = raw[obj+12:obj+12+length]
    print('validated RO string headers',len(offsets),'image',hex(image))
    for p in range(pos, min(image, 0x90000)):
        if raw[p] not in (0, 2, 64, 66):
            continue
        try:
            tag,q = read_var(raw,p,192)
        except ValueError:
            continue
        if tag != 0x17000:
            continue
        number,q = read_var(raw,q)
        length,q = read_var(raw,q)
        if number == 1 and 10000 < length < 200000:
            print('pool allocation candidate',hex(p),hex(tag),length)
            needle = encode_unsigned(length)
            at = start
            while True:
                at = raw.find(needle,at,image)
                if at < 0:
                    break
                try:
                    entries,end = pool_entries(raw,at+len(needle),length,values[1])
                except (ValueError,IndexError):
                    at += 1
                    continue
                print('pool fill candidate',hex(at),'end',hex(end),'entries',len(entries))
                output = r.DEV/'private/flutter_1_5_19_arm32/pool_strings.json'
                if not output.exists():
                    output.write_text(json.dumps({str(8+i*4-1):strings[v].decode('ascii',errors='replace') for i,v in enumerate(entries) if v in strings}), encoding='utf-8')
                for index,ref in enumerate(entries):
                    if strings.get(ref,b'') in (b'sample_gradient_decoded_bytes',b'sample_gradient_preview',b'sample_gradient_chars'):
                        print('POOL',index,'ARM32 offset',hex(8+index*4-1),strings[ref].decode())
                at += 1
    for ref,value in strings.items():
        if value in (b'sample_gradient_decoded_bytes',b'sample_gradient_preview',b'sample_gradient_chars'):
            needle = b'\x11'+encode_ref(ref)
            locations = []
            p = 0
            while True:
                p = raw.find(needle,p,image)
                if p < 0:
                    break
                locations.append(hex(p))
                p += 1
            print(value.decode(),'ref',ref,'candidate tagged ref locations',locations)


if __name__ == '__main__':
    main()
