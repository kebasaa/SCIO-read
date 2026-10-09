"""Read-only Burn reconciliation; never runs vendor installers.

Outputs use relative repository paths. Newly created private files are the only
eligible cleanup targets; budgets are cumulative, including deleted downloads.
"""
import argparse
import hashlib
import json
import subprocess
import zipfile
from pathlib import Path, PureWindowsPath
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
PRIVATE = ROOT / 'dev/private/harvestmaster_service_20261009'

def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()

def contained(base, name):
    win = PureWindowsPath(name)
    if win.is_absolute() or win.drive or '..' in win.parts:
        raise ValueError('unsafe path')
    target = (base / Path(*win.parts)).resolve()
    if not target.is_relative_to(base.resolve()) or target == base.resolve():
        raise ValueError('outside workspace')
    return target

def budget(entries, size):
    if len(entries) >= 5 or size > 512 * 1024**2 or sum(e['size'] for e in entries) + size > 2 * 1024**3:
        raise ValueError('cumulative acquisition limit')

def cleanup_eligible(base, name, entry):
    target = contained(base, name)
    if not entry.get('created_by_campaign') or entry.get('classification') != 'unrelated':
        raise ValueError('not eligible')
    if not all(entry.get(k) for k in ('sha256', 'coverage', 'rationale', 'regeneration')):
        raise ValueError('missing retained evidence')
    return target

def inspect_zip(path, remaining=4 * 1024**3):
    """Preflight only: no vendor code, no files extracted, no recursion."""
    entries = []
    with zipfile.ZipFile(path) as archive:
        for item in archive.infolist():
            contained(PRIVATE, item.filename)
            if (item.external_attr >> 16) & 0o170000 == 0o120000:
                raise ValueError('archive symlink')
            remaining -= item.file_size
            if remaining < 0: raise ValueError('extracted-content limit')
            entries.append({'name': item.filename, 'size': item.file_size, 'crc': item.CRC})
    return entries, remaining

def manifest(path, ux, attached):
    data = path.read_bytes()
    if b'<!DOCTYPE' in data.upper() or b'<!ENTITY' in data.upper():
        raise ValueError('XML entities prohibited')
    tree = ET.fromstring(data)
    if tree.tag.split('}')[-1] != 'BurnManifest':
        raise ValueError('not Burn manifest')
    out = []
    def visit(node, parent):
        tag = node.tag.split('}')[-1]
        if tag == 'Payload':
            a = dict(node.attrib)
            src = a.get('SourcePath')
            candidate = None
            if src:
                for base in (ux, attached):
                    p = contained(base, src)
                    if p.is_file():
                        candidate = p
                        break
            a.update(parent=parent, present=candidate is not None)
            if candidate:
                a.update(actual_size=candidate.stat().st_size, sha256=digest(candidate),
                         extract=candidate.relative_to(ROOT).as_posix())
                if a.get('FileSize'):
                    a['size_matches'] = int(a['FileSize']) == a['actual_size']
                if a.get('Hash'):
                    algorithm = 'sha512' if len(a['Hash']) == 128 else 'sha1'
                    a['declared_hash_algorithm'] = algorithm
                    a['declared_hash_matches'] = hashlib.new(algorithm, candidate.read_bytes()).hexdigest().lower() == a['Hash'].lower()
            a['classification'] = 'embedded' if candidate else ('remotely_referenced' if a.get('DownloadUrl') else 'unresolved')
            out.append(a)
        for child in node:
            visit(child, tag)
    visit(tree, '')
    chain = [dict(n.attrib, kind=n.tag.split('}')[-1]) for n in tree.iter()
             if n.tag.split('}')[-1] in ('MsiPackage', 'ExePackage', 'MspPackage', 'Container')]
    return dict(manifest_sha256=digest(path), payloads=out, chain=chain)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', default='dev/analysis_output/harvestmaster_service_20261009/coverage.json')
    args = parser.parse_args()
    output = contained(ROOT / 'dev', str(Path(args.output).relative_to('dev')))
    results = {'schema': 1, 'operation': 'static-read-only', 'versions': {}, 'inputs': [],
               'code_revision': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
               'driver_sha256': digest(Path(__file__)), 'working_tree': 'contains pre-existing user changes',
               'limits': {'packages': 5, 'single_package_bytes': 512 * 1024**2, 'download_bytes': 2 * 1024**3, 'extracted_bytes': 4 * 1024**3}}
    base = ROOT / 'dev/private/harvestmaster'
    for version in ('4', '5'):
        results['versions'][version] = manifest(base / f'x_mirus{version}/0',
                                              base / f'x_mirus{version}', base / f'x_mirus{version}_container')
    for folder in ('dl_mirus4', 'dl_mirus5', 'dl_troubleshooter'):
        for p in sorted((base / folder).rglob('*')):
            if p.is_file():
                results['inputs'].append(dict(path=p.relative_to(ROOT).as_posix(), size=p.stat().st_size, sha256=digest(p)))
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('x', encoding='utf8') as f:
        json.dump(results, f, indent=2)
    print(json.dumps({v: {'payloads': len(r['payloads']), 'missing': sum(not p['present'] for p in r['payloads'])} for v, r in results['versions'].items()}))

if __name__ == '__main__':
    main()
