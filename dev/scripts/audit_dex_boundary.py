"""Read DEX class definitions to distinguish service references from implementations."""
import argparse
import io
import struct
import zipfile
from pathlib import Path
import _bootstrap
from scio_offline import research as r

TARGETS = ('Landroid/hardware/ISCiO;', 'Landroid/hardware/ISCiO$Stub;',
           'Lcom/consumerphysics/android/sdk/sciosdk/ScioPhoneInternalDevice;')


def uleb(raw, off):
    value = 0
    for shift in range(0, 35, 7):
        if off >= len(raw):
            raise ValueError('truncated ULEB128')
        byte = raw[off]
        off += 1
        value |= (byte & 127) << shift
        if byte < 128:
            return value, off
    raise ValueError('oversized ULEB128')


def definitions(raw):
    if len(raw) < 112 or raw[:4] != b'dex\n' or raw[7] != 0:
        raise ValueError('not a standard DEX header')
    if struct.unpack_from('<I', raw, 40)[0] != 0x12345678:
        raise ValueError('unsupported DEX byte order')
    strings_n, strings_off, types_n, types_off = struct.unpack_from('<4I', raw, 56)
    classes_n, classes_off = struct.unpack_from('<2I', raw, 96)
    for count, off, stride in [(strings_n, strings_off, 4),
                               (types_n, types_off, 4), (classes_n, classes_off, 32)]:
        if off + count * stride > len(raw):
            raise ValueError('DEX table outside file')
    def string(index):
        if index >= strings_n:
            raise ValueError('bad string index')
        pos = struct.unpack_from('<I', raw, strings_off + index * 4)[0]
        _, pos = uleb(raw, pos)
        end = raw.find(b'\0', pos)
        if end < 0:
            raise ValueError('unterminated DEX string')
        # Class descriptors and the explicit ASCII targets need no MUTF-8 conversion.
        return raw[pos:end].decode('ascii', errors='replace')
    names = []
    for i in range(classes_n):
        index = struct.unpack_from('<I', raw, classes_off + i * 32)[0]
        if index >= types_n:
            raise ValueError('bad class type index')
        names.append(string(struct.unpack_from('<I', raw, types_off + index * 4)[0]))
    return names


def dex_members(raw, origin):
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        for name in sorted(z.namelist()):
            if name.endswith('.apk'):
                yield from dex_members(z.read(name), origin + '!' + name)
            elif name.endswith('.dex'):
                yield origin + '!' + name, z.read(name)


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--apps', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    rows, archives = [], []
    for path in sorted((a.apps / 'apk').iterdir()):
        if path.suffix.lower() not in ('.apk', '.xapk'):
            continue
        raw = path.read_bytes()
        entries = list(dex_members(raw, path.name))
        archives.append({'source': path.name, 'sha256': r.sha(raw), 'dex_count': len(entries)})
        for origin, data in entries:
            row = {'source': origin, 'sha256': r.sha(data), 'bytes': len(data)}
            try:
                names = definitions(data)
                row['class_count'] = len(names)
                row['target_definitions'] = [x for x in TARGETS if x in names]
                row['service_literal_present'] = b'SCiO_service' in data
                row['interface_literal_present'] = b'android.hardware.ISCiO' in data
                row['related_definitions'] = [x for x in names if 'iscio' in x.lower()]
            except (ValueError, struct.error) as exc:
                row['parse_error'] = str(exc)
            rows.append(row)
    r.write_new(a.output, {'archives': archives, 'dex_files': rows,
        'limits': 'Class-definition tables and literal presence only; not decompiled control flow. An absent class definition does not exclude dynamic loading, framework/vendor implementations, obfuscation, or native code. No APK executed.'})
    print('archives', len(archives), 'DEX files', len(rows),
          'parse errors', sum('parse_error' in x for x in rows))
    for target in TARGETS:
        print(target, sum(target in x.get('target_definitions', []) for x in rows))


if __name__ == '__main__':
    main()
