"""Extract only the two ARM64 libraries needed for local Blutter analysis."""
import argparse
import io
import re
import zipfile
from pathlib import Path
import _bootstrap
from scio_offline import research as r


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--apps', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    source = a.apps/'apk/SCiO+Analyzer_1.5.6_APKPure.xapk'
    target = r.DEV/'private/flutter_1_5_6_arm64'
    raw = source.read_bytes()
    with zipfile.ZipFile(io.BytesIO(raw)) as outer:
        inner_raw = outer.read('config.arm64_v8a.apk')
    rows = []
    with zipfile.ZipFile(io.BytesIO(inner_raw)) as inner:
        for name in ('libapp.so', 'libflutter.so'):
            data = inner.read('lib/arm64-v8a/' + name)
            target.mkdir(parents=True, exist_ok=True)
            path = target/name
            if path.exists():
                if path.read_bytes() != data:
                    raise ValueError('existing extracted file mismatch')
            else:
                with path.open('xb') as f:
                    f.write(data)
            row = {'member':'config.arm64_v8a.apk!lib/arm64-v8a/'+name,
                   'sha256':r.sha(data),'bytes':len(data), 'extracted_to':r.label(path)}
            if name == 'libflutter.so':
                row['dart_version_markers'] = [m.group(1).decode() for m in
                    re.finditer(rb'\x00([\d\w.-]+) \((?:stable|beta|dev)\)',data)]
            rows.append(row)
    r.write_new(a.output, {'source':source.name,'sha256':r.sha(raw),'libraries':rows,
        'limits':'Only supplied local binaries extracted; no app execution, device interaction or upload.'})
    print('Dart version markers',rows[-1]['dart_version_markers'])


if __name__ == '__main__':
    main()
