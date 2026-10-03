"""Bounded native inventory and AOT tracing prerequisites from local archives.

Literal locations are NOT code references. Never dump arbitrary snapshot strings.
"""
import argparse
import io
import re
import struct
import zipfile
from pathlib import Path
import _bootstrap
from audit_flutter import elf_sections
from scio_offline import research as r

ANCHORS = (
    'sample', 'sample_dark', 'sample_white', 'sample_white_dark',
    'sample_gradient', 'sample_white_gradient', 'sample_gradient_decoded_bytes',
    'sample_gradient_preview', 'sample_gradient_chars', 'reflectance',
    'wavelength', 'i2s_tag', 'i2s_tag_config', 'compression_version',
    'bins_checksum', 'centers_checksum', 'dead_pixels_indices_checksum',
    'n_pixels_per_bin_checksum', 'ScioFirmwareFiles', 'dsp_boot', 'dsp_dec',
    'dsp_op', 'Bad_sample_signature', 'spectro-scan', 'user_calibration',
)


def native_members(raw, origin):
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        for name in sorted(z.namelist()):
            if name.endswith('.apk'):
                yield from native_members(z.read(name), origin + '!' + name)
            elif name.endswith('.so'):
                yield origin + '!' + name, z.read(name)


def occurrences(raw, needle):
    """Bounded exact-byte search; missing needles must never produce slices."""
    if not needle:
        raise ValueError('empty needle')
    start = 0
    while True:
        pos = raw.find(needle, start)
        if pos < 0:
            return
        yield pos
        start = pos + len(needle)


def snapshot_header(raw, symbol, sections):
    for section in sections:
        delta = symbol['value'] - section['address']
        if 0 <= delta < section['size'] and section['type'] != 8:
            off = section['offset'] + delta
            data = raw[off:off + min(symbol['size'], 512)]
            # Header identification only: the hash is not a device encryption key.
            if len(data) >= 52 and data[:4] == b'\xf5\xf5\xdc\xdc':
                version = data[20:52].decode('ascii')
                features = data[52:].split(b'\0', 1)[0].decode('ascii')
                if re.fullmatch('[0-9a-f]{32}', version):
                    return {'file_offset': off, 'snapshot_format_hash': version,
                            'feature_string': features,
                            'serialized_size_field': struct.unpack_from('<Q', data, 4)[0],
                            'kind_field': struct.unpack_from('<Q', data, 12)[0]}
    return None


def inspect(raw, origin):
    row = {'source': origin, 'sha256': r.sha(raw), 'bytes': len(raw)}
    try:
        sections, symbols = elf_sections(raw)
    except (ValueError, IndexError, struct.error) as exc:
        row['parse_error'] = type(exc).__name__
        return row
    row['elf_machine'] = struct.unpack_from('<H', raw, 18)[0]
    row['symbol_count'] = len(symbols)
    # Names, not values of arbitrary constants or environment configuration.
    row['jni_exports'] = [s['name'] for s in symbols if s['name'].startswith('Java_')]
    row['snapshot_headers'] = {
        s['name']: snapshot_header(raw, s, sections) for s in symbols
        if s['name'].endswith('SnapshotData')}
    row['anchors'] = []
    for term in ANCHORS:
        for off in occurrences(raw, term.encode('ascii')):
            sec = next((s for s in sections if s['type'] != 8 and
                        s['offset'] <= off < s['offset'] + s['size']), None)
            hit = {'literal': term, 'offset': off,
                   'section': sec['name'] if sec else None}
            # Empirical length-prefix check, not a Dart object deserializer.
            if off >= 4:
                hit['preceding_u32_equals_twice_literal_length'] = (
                    struct.unpack_from('<I', raw, off - 4)[0] == 2 * len(term))
            row['anchors'].append(hit)
    return row


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--apps', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    archives, libs, seen = [], [], {}
    for path in sorted((a.apps / 'apk').iterdir()):
        if path.suffix.lower() not in ('.apk', '.xapk'):
            continue
        raw = path.read_bytes()
        members = list(native_members(raw, path.name))
        archives.append({'source': path.name, 'sha256': r.sha(raw),
                         'native_members': len(members)})
        for origin, data in members:
            digest = r.sha(data)
            if digest not in seen:
                seen[digest] = len(libs)
                libs.append(inspect(data, origin))
                libs[-1]['occurrences'] = []
            libs[seen[digest]]['occurrences'].append(origin)
    r.write_new(a.output, {'archives': archives, 'unique_libraries': libs,
        'limits': 'Inventory, exported JNI names, snapshot-format identifiers and exact literals only. No recovered AOT object-pool/code references or caller/callee graph. Library names and literal proximity do not establish scan processing. Snapshot hashes identify formats, not device keys. Archives are supplied artifacts; publisher authenticity not verified.',
        'next_trace_requirements': ['Version-matched Dart snapshot deserialization',
            'Resolve target strings through serialized object pools to code objects',
            'Disassemble identified ARM/ARM64 callers and trace Base64/JSON versus numerical processing',
            'Connect any candidate calibration table to those callers before decoder use']})
    print('archives', len(archives), 'native occurrences', sum(x['native_members'] for x in archives),
          'unique native libraries', len(libs))
    for lib in libs:
        if lib['source'].endswith('/libapp.so'):
            print(lib['source'], 'anchor hits', len(lib.get('anchors', [])),
                  'snapshot headers', len(lib.get('snapshot_headers', {})))


if __name__ == '__main__':
    main()
