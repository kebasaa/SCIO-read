"""Extract exact ARM32 libraries for the supplied newer app, with provenance."""
import argparse
import io
import re
import zipfile
from pathlib import Path
import _bootstrap
from scio_offline import research as r

p = argparse.ArgumentParser()
p.add_argument('--apps', type=Path, required=True)
p.add_argument('--output', type=Path, required=True)
a = p.parse_args()
source = a.apps/'apk/SCiO+Analyzer_1.5.19_APKPure.xapk'
raw = source.read_bytes()
target = r.DEV/'private/flutter_1_5_19_arm32'
target.mkdir(parents=True, exist_ok=True)
with zipfile.ZipFile(io.BytesIO(raw)) as archive:
    nested = archive.read('config.armeabi_v7a.apk')
rows = []
with zipfile.ZipFile(io.BytesIO(nested)) as apk:
    for name in ['libapp.so','libflutter.so']:
        data = apk.read('lib/armeabi-v7a/'+name)
        path = target/name
        if path.exists():
            if path.read_bytes() != data:
                raise ValueError('existing extraction differs')
        else:
            with path.open('xb') as f:
                f.write(data)
        row = {'member':'config.armeabi_v7a.apk!lib/armeabi-v7a/'+name,
               'sha256':r.sha(data),'bytes':len(data)}
        if name == 'libflutter.so':
            row['dart_versions'] = [m[1].decode() for m in re.finditer(rb'\x00([\d\w.-]+) \((?:stable|beta|dev)\)',data)]
        rows.append(row)
r.write_new(a.output, {'source':source.name,'sha256':r.sha(raw),'libraries':rows})
print(rows[-1].get('dart_versions'))
