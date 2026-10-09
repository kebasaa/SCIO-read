"""Bounded static decoding of already extracted Costura resources. Offline only.

The inspected loader explicitly uses DeflateStream. Never Assembly.Load,
deserialize vendor objects, run scripts, or execute the extracted payloads.
"""
import hashlib
import json
from pathlib import Path
import zlib
from audit_harvestmaster import kind, vocab_hits

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'dev/private/harvestmaster_resources_20261009'
PUBLIC = ROOT / 'dev/analysis_output/harvestmaster_resources_20261009'

def sha(data): return hashlib.sha256(data).hexdigest()

def inflate(data, limit=32 * 1024**2):
    stream = zlib.decompressobj(-15)
    decoded = stream.decompress(data, limit + 1)
    if len(decoded) > limit or stream.unconsumed_tail:
        raise ValueError('decompression limit')
    if not stream.eof or stream.unused_data:
        raise ValueError('incomplete stream or unexplained trailing bytes')
    return decoded

def write_new(name, data):
    target = (OUT / name).resolve()
    if not target.is_relative_to(OUT.resolve()) or target == OUT.resolve():
        raise ValueError('unsafe target')
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open('xb') as f: f.write(data)
    return target

def main():
    source = ROOT / 'dev/private/harvestmaster_service_20261009/decomp'
    rows = []
    total = 0
    for label in ('serviceapp', 'service134'):
        for p in sorted((source / label).glob('*')):
            if not p.is_file() or not (p.name.endswith('.compressed') or p.suffix == '.dll'):
                continue
            raw = p.read_bytes()
            row = {'source': p.relative_to(ROOT).as_posix(), 'source_sha256': sha(raw), 'source_size': len(raw)}
            try:
                data = inflate(raw) if p.name.endswith('.compressed') else raw
                name = p.name.removeprefix('costura.').removesuffix('.compressed')
                total += len(data)
                if total > 512 * 1024**2: raise ValueError('campaign expansion limit')
                row.update(decoded_size=len(data), sha256=sha(data), kind=kind(data), vocabulary=vocab_hits(data))
                path = write_new(f'assemblies/{label}/{name}', data)
                row['output'] = path.relative_to(ROOT).as_posix()
                row['status'] = 'decoded' if p.name.endswith('.compressed') else 'uncompressed-resource'
            except (ValueError, zlib.error) as exc:
                row.update(status='unsupported-or-malformed', error=str(exc))
            assert sha(p.read_bytes()) == row['source_sha256'], 'source drift'
            rows.append(row)
    # The bundle was statically dumped with ILSpy. Record every payload, not only DLLs.
    for p in sorted((OUT / 'bundle').rglob('*')):
        if p.is_file():
            data = p.read_bytes()
            rows.append({'source': 'troubleshooter-bundle/' + p.relative_to(OUT / 'bundle').as_posix(), 'sha256': sha(data), 'decoded_size': len(data), 'kind': kind(data), 'vocabulary': vocab_hits(data), 'output': p.relative_to(ROOT).as_posix(), 'status': 'bundle-extract'})
    by_hash = {}
    for row in rows:
        if row.get('sha256'): by_hash.setdefault(row['sha256'], []).append(row['source'])
    PUBLIC.mkdir(parents=True, exist_ok=True)
    with (PUBLIC / 'embedded_manifest.json').open('x', encoding='utf8') as f:
        json.dump({'schema': 1, 'offline': True, 'decoded_bytes': total, 'records': rows, 'hash_provenance': by_hash}, f, indent=2)
    print(json.dumps({'records': len(rows), 'unique_hashes': len(by_hash), 'decoded_bytes': total, 'failures': [r for r in rows if r['status'] == 'unsupported-or-malformed']}))

if __name__ == '__main__': main()
