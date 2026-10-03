"""Scan full executable segments for narrowly allowlisted field references."""
import argparse
from pathlib import Path
import re
import _bootstrap
from scio_offline.arm64_refs import executable_segments, scan_pool_loads, direct_calls
from scio_offline.native_index import LABELS
from scio_offline.research import DEV, sha, write_new

p = argparse.ArgumentParser()
p.add_argument('--output', type=Path, required=True)
a = p.parse_args()
root = DEV/'private/flutter_1_5_6_analysis_native_v3'
pool = {}
labels = set(LABELS) | {'sampleDark','sampleGradient','whiteReference','calibrationReading',
                      'device_i2s','saveCalibration','calibrate','spectrum','firmwareFileVersions'}
for line in (root/'pp.txt').read_text(encoding='utf-8').splitlines():
    m = re.fullmatch(r'\[pp\+(0x[0-9a-f]+)\] String: "([^"\n]+)"', line)
    if m and m[2] in labels:
        pool[int(m[1],16)] = m[2]
raw = (DEV/'private/flutter_1_5_6_arm64/libapp.so').read_bytes()
hits = []
callers = []
for base, code in executable_segments(raw):
    for address, target in direct_calls(code, base):
        if target in (0x31db44, 0x31dd48, 0xa0a09c, 0x6ff260):
            callers.append({'address':hex(address), 'target':hex(target)})
    for hit in scan_pool_loads(code, base):
        if hit['offset'] in pool:
            hits.append({'address':hex(hit['address']), 'pool_offset':hex(hit['offset']),
                         'label':pool[hit['offset']]})
write_new(a.output, {'binary_sha256':sha(raw), 'hits':hits, 'direct_callers':callers,
                    'limits':'Instruction-pattern references only, not function boundaries, runtime reachability or codec semantics.'})
for hit in hits:
    print(hit['address'], hit['label'])
print('Direct callers:', callers)
