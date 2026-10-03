"""Record reviewed Flutter paths and the exact allowlisted embedded scan fixture."""
import argparse
import base64
import json
from pathlib import Path
import re
import struct
import _bootstrap
from scio_offline import research as r


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    private = r.DEV/'private'
    dump = private/'flutter_1_5_6_analysis_native_v3'
    source = dump/'asm/synthetic_native.dart'
    assembly = source.read_text(encoding='utf-8')
    assert 'addr: 0xa0a09c, size: 0x2d0' in assembly
    evidence = [
        ('request_builder', source, '0xa0a09c', '0xa0a240: r2 = "sample"',
         'Loads sample object fields 0x7/0xb/0xf into sample/sample_dark/sample_gradient map values; corresponding white object fields become sample_white/sample_white_dark/sample_white_gradient. No numerical transform in this builder.'),
        ('reading_parser', private/'native_ranges/31db28.txt', '0x31db44', '0x31dd14: stur w1, [x0, #0xb]',
         'Reads sample/sampleDark/sampleGradient from an input map, checks String types, and stores them at offsets 0x7/0xb/0xf. Timestamp is separately converted and stored at 0x13. No blob transform in this parser.'),
        ('white_serializer', private/'native_ranges/31db28.txt', '0x31dd48', '0x31de10: bl #0x304d28',
         'Emits the three existing reading strings as sample_white/sample_white_dark/sample_white_gradient plus a separately formatted timestamp.'),
        ('i2s_getter', private/'native_ranges/6ff1b8.txt', '0x6ff260', 'String: "device_i2s"',
         'Reads device_i2s from stored state. Request builder calls this accessor before inserting i2s_tag_config. No key derivation shown by this path.'),
        ('event_reading_parser', private/'native_ranges/849bc4.txt', '0x849cf8', '0x849dec: bl #0x31db44',
         'Parses event type and nullable reading map, then delegates that reading to the string-preserving parser; also reads errorInfo.'),
        ('embedded_success_event', private/'native_ranges/849bc4.txt', '0x849ca4', '0x849cc4: bl #0x31db44',
         'Passes constant map at pp+0x385c8 to the same reading parser and combines it with a success enum. This is an app fixture, not a newly captured scan or spectral truth.'),
    ]
    rows = []
    for name, path, addr, anchor, observation in evidence:
        raw = path.read_bytes()
        if anchor not in raw.decode('utf-8'):
            raise ValueError('evidence anchor absent: '+name)
        rows.append({'id':name, 'source':r.label(path), 'sha256':r.sha(raw),
                     'address':addr, 'anchor':anchor, 'observation':observation})
    pool_raw = (dump/'pp.txt').read_bytes()
    text = pool_raw.decode('utf-8')
    match = re.search(r'^\[pp\+0x385c8\][^\n]*\n(.*?)(?=^\[pp\+)', text, re.M|re.S)
    if not match:
        raise ValueError('fixture map absent')
    blobs = {}
    for key, role in [('sample','sample'),('sampleDark','sample_dark'),('sampleGradient','sample_gradient')]:
        field = re.search(r'^  "'+key+r'": ("(?:[^"\\]|\\.)*")', match[1], re.M)
        if not field:
            raise ValueError('fixture field absent: '+key)
        value = json.loads(field[1])
        raw = base64.b64decode(''.join(value.split()), validate=True)
        blobs[role] = {'sha256':r.sha(raw), 'bytes':len(raw),
                       'header_u32le':list(struct.unpack('<II',raw[:8])),
                       'base64':base64.b64encode(raw).decode()}
    known = r.manifest()['blobs']
    # Corpus manifest stores blob rows rather than keyed hashes.
    hashes = {row['sha256'] for row in known} if isinstance(known,list) else set(known)
    for value in blobs.values():
        value['already_in_corpus_manifest'] = value['sha256'] in hashes
    report = {'schema':1,
        'target_sha256':r.sha((private/'flutter_1_5_6_arm64/libapp.so').read_bytes()),
        'scope':'Supplied Analyzer 1.5.6 ARM64 only; static reviewed paths, not exhaustive app coverage.',
        'observations':rows,
        'fixture':{'pool_offset':'0x385c8','pool_sha256':r.sha(pool_raw),'blobs':blobs,
                   'device_identity':'unknown','spectral_truth':None,
                   'limits':'Fixture timestamp and success enum do not establish physical capture, device identity or correct spectral output.'},
        'remaining':'Trace native-platform producer and request consumer. Missing function metadata required bounded raw disassembly. Neither encryption nor compression is established or excluded.'}
    r.write_new(a.output, report)
    print('Reviewed observations:',len(rows))
    for role, data in blobs.items():
        print(role, data['bytes'], data['sha256'], 'known:', data['already_in_corpus_manifest'])


if __name__ == '__main__':
    main()
