"""Extract the exact modern APK's DEX inputs, preserving hashes and provenance."""
import argparse
from pathlib import Path
import _bootstrap
from audit_dex_boundary import dex_members
from scio_offline import research as r

p = argparse.ArgumentParser()
p.add_argument('--apps', type=Path, required=True)
p.add_argument('--output', type=Path, required=True)
a = p.parse_args()
source = a.apps/'apk/SCiO+Analyzer_1.5.6_APKPure.xapk'
raw = source.read_bytes()
directory = r.DEV/'private/analyzer_1_5_6_dex'
directory.mkdir(parents=True, exist_ok=True)
rows = []
for i, (origin, data) in enumerate(dex_members(raw, source.name)):
    path = directory/f'input_{i}.dex'
    if path.exists():
        if path.read_bytes() != data:
            raise ValueError('existing DEX differs')
    else:
        with path.open('xb') as f:
            f.write(data)
    rows.append({'source':origin, 'sha256':r.sha(data), 'bytes':len(data), 'path':r.label(path)})
tool = r.DEV/'private/jadx-1.5.6.zip'
r.write_new(a.output, {'source':source.name, 'sha256':r.sha(raw), 'dex':rows,
    'tool':{'source':'https://github.com/skylot/jadx/releases/tag/v1.5.6',
            'archive_sha256':r.sha(tool.read_bytes()), 'version':'1.5.6'},
    'limits':'Extraction only. Tool and APK happen to have the same version number; they are independent products.'})
print('Extracted DEX files:',len(rows))
