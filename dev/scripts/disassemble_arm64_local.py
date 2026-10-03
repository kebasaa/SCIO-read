"""Bounded raw disassembly using the already unpacked private Capstone library.

Run with WSL Python. Raw dumps stay private; ELF virtual addresses are not file
offsets. No code from the analyzed application is executed.
"""
import argparse
import ctypes as c
import hashlib
import json
from pathlib import Path
import re
import struct

DEV = Path(__file__).resolve().parents[1]


class Instruction(c.Structure):
    _fields_ = [('id', c.c_uint), ('address', c.c_uint64), ('size', c.c_uint16),
                ('bytes', c.c_uint8 * 16), ('mnemonic', c.c_char * 32),
                ('op_str', c.c_char * 160), ('detail', c.c_void_p)]


def virtual_bytes(raw, address, size):
    if raw[:6] != b'\x7fELF\x02\x01' or struct.unpack_from('<H', raw, 18)[0] != 183:
        raise ValueError('expected little-endian ARM64 ELF')
    offset = struct.unpack_from('<Q', raw, 32)[0]
    entry_size, count = struct.unpack_from('<HH', raw, 54)
    for i in range(count):
        typ, flags, off, va, _, length, _, _ = struct.unpack_from('<IIQQQQQQ', raw, offset+i*entry_size)
        if typ == 1 and flags & 1 and va <= address and address+size <= va+length:
            return raw[off+address-va:off+address-va+size]
    raise ValueError('range is not fully inside an executable file-backed segment')


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--address', type=lambda x: int(x, 0), required=True)
    p.add_argument('--size', type=lambda x: int(x, 0), required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    if a.address % 4 or a.size % 4 or not 0 < a.size <= 65536:
        p.error('aligned range of at most 65536 bytes required')
    if not a.output.resolve().is_relative_to(DEV/'private'):
        p.error('raw disassembly must remain private')
    binary = DEV/'private/flutter_1_5_6_arm64/libapp.so'
    raw = binary.read_bytes()
    code = virtual_bytes(raw, a.address, a.size)
    lib = c.CDLL(str(DEV/'private/native_prefix/usr/lib/x86_64-linux-gnu/libcapstone.so.4'))
    lib.cs_open.argtypes = [c.c_int, c.c_int, c.POINTER(c.c_size_t)]
    lib.cs_disasm.argtypes = [c.c_size_t, c.c_void_p, c.c_size_t, c.c_uint64, c.c_size_t, c.POINTER(c.POINTER(Instruction))]
    lib.cs_disasm.restype = c.c_size_t
    lib.cs_free.argtypes = [c.POINTER(Instruction), c.c_size_t]
    lib.cs_close.argtypes = [c.POINTER(c.c_size_t)]
    handle = c.c_size_t()
    if lib.cs_open(1, 0, c.byref(handle)) != 0:
        raise RuntimeError('cannot initialize ARM64 Capstone')
    instructions = c.POINTER(Instruction)()
    count = lib.cs_disasm(handle, code, len(code), a.address, 0, c.byref(instructions))
    pool = {}
    for line in (DEV/'private/flutter_1_5_6_analysis_native_v3/pp.txt').read_text().splitlines():
        m = re.match(r'\[pp\+(0x[0-9a-f]+)\] (.*)', line)
        if m:
            pool[int(m[1], 16)] = m[2]
    lines = []
    pending = None
    for ins in instructions[:count]:
        mnemonic, operands = ins.mnemonic.decode(), ins.op_str.decode()
        annotation = ''
        direct = re.fullmatch(r'x\d+, \[x27(?:, #(0x[0-9a-f]+|\d+))?\]', operands)
        if mnemonic == 'ldr' and direct:
            offset = int(direct[1] or '0', 0)
            annotation = f' ; pp+{offset:#x}: '+pool.get(offset, '<unresolved>')
        if pending:
            reg, high = pending
            load = re.fullmatch(r'x\d+, \['+reg+r'(?:, #(0x[0-9a-f]+|\d+))?\]', operands)
            if mnemonic == 'ldr' and load:
                offset = high+int(load[1] or '0', 0)
                annotation = f' ; pp+{offset:#x}: '+pool.get(offset, '<unresolved>')
        add = re.fullmatch(r'(x\d+), x27, #(0x[0-9a-f]+|\d+)(, lsl #12)?', operands)
        pending = (add[1], int(add[2], 0) << (12 if add[3] else 0)) if mnemonic == 'add' and add else None
        lines.append(f'{ins.address:#x}: {mnemonic} {operands}{annotation}')
    lib.cs_free(instructions, count)
    lib.cs_close(c.byref(handle))
    a.output.parent.mkdir(parents=True, exist_ok=True)
    with a.output.open('x') as output:
        output.write('\n'.join(lines)+'\n')
    print(json.dumps({'address':hex(a.address),'requested_bytes':a.size,'instructions':count,
                      'binary_sha256':hashlib.sha256(raw).hexdigest()}))


if __name__ == '__main__':
    main()
