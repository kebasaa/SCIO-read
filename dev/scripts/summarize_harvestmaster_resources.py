"""Offline coverage accounting; no vendor code or serialized object execution."""
import collections
import json
from pathlib import Path
from audit_embedded_harvestmaster import ROOT, OUT, PUBLIC, sha

def main():
    embedded = json.loads((PUBLIC / 'embedded_manifest.json').read_text())
    resources = json.loads((PUBLIC / 'resource_manifest_v2.json').read_text())
    verified = 0
    for row in embedded['records']:
        if row.get('source_sha256'):
            assert sha((ROOT / row['source']).read_bytes()) == row['source_sha256']
            verified += 1
        assert sha((ROOT / row['output']).read_bytes()) == row['sha256']
    assets = []
    for path in sorted((OUT / 'vendor').rglob('*')):
        if path.is_file() and path.suffix not in ('.cs', '.resx', '.csproj', '.config'):
            data = path.read_bytes()
            assets.append({'path': path.relative_to(ROOT).as_posix(), 'size': len(data), 'sha256': sha(data), 'extension': path.suffix})
    scripts = {}
    for row in resources['resources']:
        if row['name'] == 'ggDefaultScriptHashes' and row['binary']:
            entries = json.loads((ROOT / row['output']).read_bytes())
            scripts[row['sha256']] = {'entries': len(entries), 'fields': sorted({key for entry in entries for key in entry}), 'grain_gage_types': sorted({entry.get('GrainGageType', '') for entry in entries}), 'filenames': sorted({entry.get('FileName', '') for entry in entries})}
    report = {
        'offline': True, 'vendor_execution': False, 'requests': 0,
        'embedded_records': len(embedded['records']),
        'unique_payload_hashes': len(embedded['hash_provenance']),
        'kinds': dict(collections.Counter(r['kind'] for r in embedded['records'])),
        'source_hashes_reverified': verified,
        'all_recovered_payload_hashes_reverified': True,
        'vendor_decompiled_directories': len(list((OUT / 'vendor').iterdir())),
        'resx_entries': len(resources['resources']),
        'binary_resx_entries': sum(r['binary'] for r in resources['resources']),
        'unique_binary_resx_hashes': len({r['sha256'] for r in resources['resources'] if r['binary']}),
        'nested_zip_resources': sum('zip_entries' in r for r in resources['resources']),
        'non_resx_vendor_assets': assets,
        'script_hash_catalogs': scripts,
        'limits': 'Third-party assemblies inventoried, not fully decompiled; serialized graphics retained without deserialization. No claim of exhaustive instruction-level analysis.'
    }
    with (PUBLIC / 'coverage.json').open('x', encoding='utf8') as stream:
        json.dump(report, stream, indent=2)
    print(json.dumps({k: v for k, v in report.items() if k not in ('non_resx_vendor_assets', 'script_hash_catalogs')}))

if __name__ == '__main__': main()
