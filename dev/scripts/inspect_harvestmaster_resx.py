"""Inspect ILSpy-resx data without deserializing vendor objects or running scripts."""
import base64
import argparse
import hashlib
import io
import json
from pathlib import Path
import stat
import xml.etree.ElementTree as ET
import zipfile
from audit_harvestmaster import kind, vocab_hits
from audit_embedded_harvestmaster import ROOT, OUT, PUBLIC, sha, write_new

def parse_resx(data):
    if b'<!DOCTYPE' in data.upper() or b'<!ENTITY' in data.upper(): raise ValueError('XML entities prohibited')
    tree = ET.fromstring(data)
    for node in tree.findall('data'):
        value = node.findtext('value') or ''
        binary = 'base64' in node.get('mimetype', '') or 'System.Byte[]' in node.get('type', '')
        if binary:
            if len(value) > 48 * 1024**2: raise ValueError('encoded resource limit')
            decoded = base64.b64decode(''.join(value.split()), validate=True)
            if len(decoded) > 32 * 1024**2: raise ValueError('decoded resource limit')
            yield node.attrib, decoded
        else:
            yield node.attrib, value.encode('utf8')

def zip_entries(data, limit=128 * 1024**2):
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        for item in archive.infolist():
            p = Path(item.filename.replace('\\', '/'))
            if p.is_absolute() or '..' in p.parts or ':' in item.filename or stat.S_ISLNK(item.external_attr >> 16):
                raise ValueError('unsafe ZIP path')
            if item.is_dir(): continue
            limit -= item.file_size
            if limit < 0 or item.file_size > 32 * 1024**2: raise ValueError('archive limit')
            with archive.open(item) as stream: content = stream.read(32 * 1024**2 + 1)
            if len(content) != item.file_size: raise ValueError('length mismatch')
            yield item.filename, content

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', default='resource_manifest_v2.json')
    args = parser.parse_args()
    if Path(args.output).name != args.output or not args.output.endswith('.json'):
        raise ValueError('output must be a JSON basename')
    roots = [ROOT / 'dev/private/harvestmaster_service_20261009/decomp', OUT / 'decomp', OUT / 'vendor']
    rows = []
    for root in roots:
        for path in sorted(root.rglob('*.resx')):
            raw = path.read_bytes()
            for attributes, data in parse_resx(raw):
                binary = 'base64' in attributes.get('mimetype', '') or 'System.Byte[]' in attributes.get('type', '')
                row = {'source': path.relative_to(ROOT).as_posix(), 'source_sha256': sha(raw), 'name': attributes.get('name'), 'type': attributes.get('type'), 'mimetype': attributes.get('mimetype'), 'size': len(data), 'sha256': sha(data), 'binary': binary, 'kind': kind(data), 'vocabulary': vocab_hits(data)}
                if binary:
                    target = OUT / 'assets' / (sha(data) + '.bin')
                    if not target.exists(): write_new('assets/' + target.name, data)
                    row['output'] = target.relative_to(ROOT).as_posix()
                    if zipfile.is_zipfile(io.BytesIO(data)):
                        row['zip_entries'] = []
                        for name, content in zip_entries(data):
                            target = OUT / 'assets' / (sha(content) + '.bin')
                            if not target.exists(): write_new('assets/' + target.name, content)
                            row['zip_entries'].append({'name': name, 'size': len(content), 'sha256': sha(content), 'kind': kind(content), 'vocabulary': vocab_hits(content), 'output': target.relative_to(ROOT).as_posix()})
                rows.append(row)
            assert sha(path.read_bytes()) == sha(raw), 'source drift'
    # Compare actual recovered bytes with the earlier broad inventory, retaining provenance.
    old = json.loads((ROOT / 'dev/private/harvestmaster/audit_20261009/inventory.json').read_text())
    old_hashes = {r['sha256'] for r in old['files']}
    manifest = json.loads((PUBLIC / 'embedded_manifest.json').read_text())
    comparison = [{'sha256': h, 'previously_in_broad_inventory': h in old_hashes, 'sources': sources}
                  for h, sources in manifest['hash_provenance'].items()]
    with (PUBLIC / args.output).open('x', encoding='utf8') as f:
        json.dump({'schema': 1, 'resources': rows, 'prior_hash_comparison': comparison}, f, indent=2)
    print(json.dumps({'resources': len(rows), 'binary': sum(r['binary'] for r in rows), 'archives': sum('zip_entries' in r for r in rows), 'recovered_hashes_new_to_inventory': sum(not r['previously_in_broad_inventory'] for r in comparison)}))

if __name__ == '__main__': main()
