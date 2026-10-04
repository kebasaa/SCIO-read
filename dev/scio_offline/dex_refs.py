"""Find code references to selected strings and static fields in DEX bytecode.

Decompiled Java can drop methods (every JADX run here reported errors), and javac
inlines ``static final String`` constants, so "the constant is declared but no
Java file uses it" is only as good as the decompilation. This scans the method
bodies themselves for:

* ``const-string`` (0x1a, format 21c) and ``const-string/jumbo`` (0x1b, 31c)
  loading a target string, and
* ``sget-object`` (0x62, 21c) reading a target static field.

Matching is syntactic at every 16-bit code unit inside each ``code_item``; there
is no full instruction-boundary decoder, so a hit is a *candidate* (an operand
word can alias an opcode), while zero hits bound direct references. Strings built
at run time (concatenation, resources, reflection) are outside its coverage.
"""
from __future__ import annotations

import struct

CONST_STRING, CONST_STRING_JUMBO, SGET_OBJECT = 0x1A, 0x1B, 0x62


def uleb(raw: bytes, off: int) -> tuple[int, int]:
    value = 0
    for shift in range(0, 35, 7):
        if off >= len(raw):
            raise ValueError("truncated ULEB128")
        byte = raw[off]
        off += 1
        value |= (byte & 0x7F) << shift
        if byte < 0x80:
            return value, off
    raise ValueError("oversized ULEB128")


class Dex:
    def __init__(self, raw: bytes):
        if len(raw) < 112 or raw[:4] != b"dex\n":
            raise ValueError("not a DEX file")
        if struct.unpack_from("<I", raw, 40)[0] != 0x12345678:
            raise ValueError("unsupported DEX byte order")
        self.raw = raw
        (self.strings_n, self.strings_off, self.types_n, self.types_off,
         _, _, self.fields_n, self.fields_off, self.methods_n, self.methods_off,
         self.classes_n, self.classes_off) = struct.unpack_from("<12I", raw, 56)

    def string(self, index: int) -> str:
        pos = struct.unpack_from("<I", self.raw, self.strings_off + 4 * index)[0]
        _, pos = uleb(self.raw, pos)
        end = self.raw.index(b"\0", pos)
        return self.raw[pos:end].decode("utf-8", errors="replace")

    def type_name(self, index: int) -> str:
        return self.string(struct.unpack_from("<I", self.raw, self.types_off + 4 * index)[0])

    def field(self, index: int) -> tuple[str, str]:
        cls, _, name = struct.unpack_from("<HHI", self.raw, self.fields_off + 8 * index)
        return self.type_name(cls), self.string(name)

    def method(self, index: int) -> tuple[str, str]:
        cls, _, name = struct.unpack_from("<HHI", self.raw, self.methods_off + 8 * index)
        return self.type_name(cls), self.string(name)

    def code_items(self):
        """Yield (method_index, start, end) of every method body."""
        raw = self.raw
        for i in range(self.classes_n):
            pos = struct.unpack_from("<I", raw, self.classes_off + 32 * i + 24)[0]
            if not pos:
                continue
            counts = []
            for _ in range(4):
                value, pos = uleb(raw, pos)
                counts.append(value)
            for _ in range(counts[0] + counts[1]):
                _, pos = uleb(raw, pos)
                _, pos = uleb(raw, pos)
            for count in counts[2:]:
                method = 0
                for _ in range(count):
                    delta, pos = uleb(raw, pos)
                    method += delta
                    _, pos = uleb(raw, pos)
                    code, pos = uleb(raw, pos)
                    if not code:
                        continue
                    size = struct.unpack_from("<I", raw, code + 12)[0] * 2
                    yield method, code + 16, code + 16 + size


def scan_code(raw: bytes, start: int, end: int, strings: set[int], fields: set[int]):
    """Candidate (offset, opcode, index) references inside one method body."""
    for at in range(start, end - 3, 2):
        op = raw[at]
        if op == CONST_STRING and struct.unpack_from("<H", raw, at + 2)[0] in strings:
            yield at, op, struct.unpack_from("<H", raw, at + 2)[0]
        elif op == CONST_STRING_JUMBO and at + 6 <= end and struct.unpack_from("<I", raw, at + 2)[0] in strings:
            yield at, op, struct.unpack_from("<I", raw, at + 2)[0]
        elif op == SGET_OBJECT and struct.unpack_from("<H", raw, at + 2)[0] in fields:
            yield at, op, struct.unpack_from("<H", raw, at + 2)[0]


def find_references(raw: bytes, substrings, field_names) -> dict:
    """Target strings/fields present in a DEX, and candidate code references to them."""
    dex = Dex(raw)
    strings = {i: dex.string(i) for i in range(dex.strings_n)}
    target_strings = {i for i, s in strings.items() if any(t in s for t in substrings)}
    target_fields = {i for i in range(dex.fields_n) if dex.field(i)[1] in field_names}
    refs = []
    for method, start, end in dex.code_items():
        for at, op, index in scan_code(raw, start, end, target_strings, target_fields):
            cls, name = dex.method(method)
            target = strings[index] if op != SGET_OBJECT else ".".join(dex.field(index))
            refs.append({"class": cls, "method": name, "offset": at,
                         "opcode": {CONST_STRING: "const-string", CONST_STRING_JUMBO: "const-string/jumbo",
                                    SGET_OBJECT: "sget-object"}[op],
                         "target": target})
    return {"strings": sorted(strings[i] for i in target_strings),
            "fields": sorted(".".join(dex.field(i)) for i in target_fields),
            "references": refs}
