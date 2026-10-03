"""Verify selected ARM call edges and preserve reviewed diagnostic findings."""
import argparse
from pathlib import Path
import _bootstrap
from trace_arm32_diagnostics import segments,direct_calls
from scio_offline import research as r


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);a=parser.parse_args()
    directory=r.DEV/'private/flutter_1_5_19_arm32'
    raw=(directory/'libapp.so').read_bytes()
    expected='9d46ae6000a652971848fecb894402727183ca07c986762198283564d9aecd9c'
    if r.sha(raw)!=expected:raise ValueError('unexpected binary')
    edges=dict(edge for off,va,n in segments(raw) for edge in direct_calls(raw[off:off+n-n%4],va))
    reviewed=[(0xc74384,0xc75bc0),(0xc75c80,0x9c255c),
              (0x9c25c4,0xc75cac),(0x9c25e4,0xc75cac),(0x9c2604,0xc75cac),
              (0x9c2644,0xc75cac),(0x9c2684,0xc75cac),(0x9c26c4,0xc75cac),
              (0xc75f58,0xa495e4),(0xa49604,0x61db14),(0x61dbe8,0x61dcfc),
              (0x61dc0c,0x61dc1c),(0xc744ec,0xc75364)]
    for source,target in reviewed:
        if edges.get(source)!=target:raise ValueError('call edge changed')
    inputs=[]
    for name in ('caller_c74100.txt','validator_c75bc0.txt','validation_map_9c255c.txt',
                 'decoder_a495e4.txt','base64_61db14.txt','map_contains_52e700.txt','string_prepare_3e35a4.txt'):
        data=(directory/name).read_bytes()
        inputs.append({'path':r.label(directory/name),'sha256':r.sha(data)})
    r.write_new(a.output,{'binary_sha256':expected,'private_evidence':inputs,
        'verified_direct_call_edges':[{'call':hex(s),'target':hex(t)} for s,t in reviewed],
        'findings':[
            {'address':'0xc75cac','finding':'Per-role validation helper dynamically constructs _chars, _preview, _decoded_bytes, _empty, _too_small, _invalid_base64 labels. Explains why full-name-only pool searches missed the producer.'},
            {'address':'0xc75f58','finding':'Calls wrapper 0xa495e4, which directly calls Base64-decoder-shaped routine 0x61db14. Output length, not wavelength data, is stored as decoded_bytes.'},
            {'address':'0x61dc1c','finding':'Padding finalizer emits Missing padding character and Invalid length, must be multiple of four. Decode loop includes six-bit accumulation; consistent with Base64, not JPEG or ciphertext decryption.'},
            {'address':'0xc75fb8','finding':'Untag decoded byte length then compare against 4. Length below 4 adds role_too_small. No exact SCIO frame-size check, status/checksum test, or 331-band calculation in this helper.'},
            {'address':'0xc7616c','finding':'Recognized decode exception stores tagged -1 in decoded_bytes and adds role_invalid_base64; unrelated exceptions are rethrown.'},
            {'address':'0x9c255c','finding':'sample and sample_dark are required; sample_gradient can be empty. White roles are checked only when map contains their keys; present white sample/dark required, gradient optional.'},
            {'address':'0x9c2840','finding':'Adds sample_empty_while_gradient_has_data when prepared sample string is empty and prepared gradient string nonempty.'},
            {'address':'0x9c28c0','finding':'Preview is prepared input string, kept intact through 96 code units; longer strings use first 96 followed by ellipsis. It is not a preview of decoded spectral values.'}
        ],
        'limits':'Static reviewed data flow, not execution of the Dart application. Exact string coercion, trimming whitespace set, exception types and Base64 variants not fully resolved. No emulator-equivalence claim. Gate acceptance is not server acceptance or a valid device spectrum. No conclusion about opaque-body encryption/compression.',
        'device_server_activity':'None'})
    print('Verified direct call edges:',len(reviewed))


if __name__=='__main__':main()
