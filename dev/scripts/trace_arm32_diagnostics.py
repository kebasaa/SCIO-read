"""Target-specific ARM32 pool-load search and optional private disassembly."""
import argparse
import json
import struct
import hashlib
from pathlib import Path

DEV = Path(__file__).resolve().parents[1]


def direct_calls(code, address=0):
    """ARM-state immediate BL only; excludes BLX and indirect calls."""
    if address % 4 or len(code) % 4:
        raise ValueError('unaligned ARM code')
    for offset in range(0,len(code),4):
        word=struct.unpack_from('<I',code,offset)[0]
        if word & 0x0f000000 != 0x0b000000 or word >> 28 == 15:
            continue
        displacement=word & 0xffffff
        if displacement & 0x800000: displacement-=1<<24
        yield address+offset,address+offset+8+displacement*4


def segments(raw):
    if raw[:6] != b'\x7fELF\x01\x01' or struct.unpack_from('<H',raw,18)[0] != 40:
        raise ValueError('expected little-endian ARM ELF')
    off = struct.unpack_from('<I',raw,28)[0]
    size,count = struct.unpack_from('<HH',raw,42)
    for i in range(count):
        typ,p,va,_,length,_,flags,_ = struct.unpack_from('<IIIIIIII',raw,off+i*size)
        if typ == 1 and flags & 1:
            yield p,va,length


def pool_load(a,b):
    # ADD immediate from tagged PP r5, then positive immediate LDR via result.
    if a & 0x0fff0000 != 0x02850000 or b & 0x0ff00000 != 0x05900000:
        return None
    if (a>>28) != (b>>28) or (a>>12)&15 != (b>>16)&15:
        return None
    imm,rot = a&255,((a>>8)&15)*2
    high = ((imm>>rot)|(imm<<(32-rot)))&0xffffffff if rot else imm
    return high+(b&4095)


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--address',type=lambda s:int(s,0))
    p.add_argument('--size',type=lambda s:int(s,0),default=2048)
    p.add_argument('--output',type=Path)
    p.add_argument('--callers',type=lambda s:int(s,0))
    args=p.parse_args()
    raw=(DEV/'private/flutter_1_5_19_arm32/libapp.so').read_bytes()
    if hashlib.sha256(raw).hexdigest() != '9d46ae6000a652971848fecb894402727183ca07c986762198283564d9aecd9c':
        raise ValueError('unsupported binary')
    if args.callers is not None:
        for off,va,n in segments(raw):
            for caller,target in direct_calls(raw[off:off+n-n%4],va):
                if target==args.callers: print(hex(caller),hex(target))
        return
    pool=json.loads((DEV/'private/flutter_1_5_19_arm32/pool_strings.json').read_text())
    if args.address is None:
        for off,va,n in segments(raw):
            for q in range(off,off+n-4,4):
                key=pool_load(*struct.unpack_from('<II',raw,q))
                label=pool.get(str(key),'')
                if label in ('sample_gradient_chars','sample_gradient_decoded_bytes','sample_gradient_preview'):
                    print(hex(va+q-off),hex(key),label)
        return
    if not args.output or not args.output.resolve().is_relative_to(DEV/'private'):
        p.error('disassembly output must be private')
    if args.address%4 or args.size%4 or not 0<args.size<=65536:
        p.error('bounded aligned range required')
    code=None
    for off,va,n in segments(raw):
        if va<=args.address and args.address+args.size<=va+n:
            code=raw[off+args.address-va:off+args.address-va+args.size]
    if code is None: raise ValueError('range outside executable segment')
    import ctypes as c
    from disassemble_arm64_local import Instruction
    lib=c.CDLL(str(DEV/'private/native_prefix/usr/lib/x86_64-linux-gnu/libcapstone.so.4'))
    lib.cs_open.argtypes=[c.c_int,c.c_int,c.POINTER(c.c_size_t)]
    lib.cs_disasm.argtypes=[c.c_size_t,c.c_void_p,c.c_size_t,c.c_uint64,c.c_size_t,c.POINTER(c.POINTER(Instruction))]
    lib.cs_disasm.restype=c.c_size_t
    lib.cs_free.argtypes=[c.POINTER(Instruction),c.c_size_t]
    lib.cs_close.argtypes=[c.POINTER(c.c_size_t)]
    handle=c.c_size_t()
    if lib.cs_open(0,0,c.byref(handle)): raise RuntimeError('Capstone ARM failed')
    ins=c.POINTER(Instruction)()
    count=lib.cs_disasm(handle,code,len(code),args.address,0,c.byref(ins))
    lines=[]
    previous=None
    for row in ins[:count]:
        word=int.from_bytes(bytes(row.bytes[:4]),'little')
        key=pool_load(previous,word) if previous is not None else None
        if word&0x0fff0000==0x05950000: key=word&4095
        annotation=' ; '+repr(pool[str(key)]) if str(key) in pool else ''
        lines.append(f'{row.address:#x}: {row.mnemonic.decode()} {row.op_str.decode()}{annotation}')
        previous=word
    lib.cs_free(ins,count)
    lib.cs_close(c.byref(handle))
    args.output.parent.mkdir(parents=True,exist_ok=True)
    with args.output.open('x') as f: f.write('\n'.join(lines)+'\n')
    print(json.dumps({'address':hex(args.address),'instructions':count}))


if __name__=='__main__': main()
