"""Narrow ARM64 object-pool load scanner; no executable code is run."""
import struct


def direct_calls(code, base=0):
    for i in range(0, len(code)-3, 4):
        word = struct.unpack_from('<I', code, i)[0]
        if word & 0xfc000000 == 0x94000000:
            displacement = word & 0x03ffffff
            if displacement & 0x02000000:
                displacement -= 0x04000000
            yield base+i, base+i+4*displacement


def scan_pool_loads(code, base=0):
    """Direct X-register LDR from x27, or adjacent ADD(x27)/LDR pair.

    Does not follow register copies, branches, computed indices or general dataflow.
    Returns instruction addresses and numeric offsets, never pool contents.
    """
    pending = None
    for i in range(0, len(code)-3, 4):
        word = struct.unpack_from('<I', code, i)[0]
        rn, rd = (word >> 5) & 31, word & 31
        if word & 0xffc00000 == 0xf9400000:
            offset = ((word >> 10) & 4095) * 8
            if rn == 27:
                yield {'address': base+i, 'offset': offset}
            elif pending is not None and rn == pending[0]:
                yield {'address': base+i, 'offset': pending[1]+offset}
        pending = None
        if word & 0xff800000 == 0x91000000 and rn == 27:
            pending = (rd, ((word >> 10) & 4095) << (12 if word & (1 << 22) else 0))


def executable_segments(raw):
    if raw[:6] != b'\x7fELF\x02\x01' or struct.unpack_from('<H', raw, 18)[0] != 183:
        raise ValueError('expected little-endian ARM64 ELF')
    offset = struct.unpack_from('<Q', raw, 32)[0]
    entry_size, count = struct.unpack_from('<HH', raw, 54)
    for i in range(count):
        typ, flags, off, va, _, length, _, _ = struct.unpack_from('<IIQQQQQQ', raw, offset+i*entry_size)
        if typ == 1 and flags & 1:
            if off+length > len(raw):
                raise ValueError('truncated executable segment')
            yield va, raw[off:off+length]
