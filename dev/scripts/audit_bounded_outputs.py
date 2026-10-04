"""Verify campaign artifacts, including compressed manifests, without printing data."""
import argparse
import gzip
import importlib.util
import json
import re
import subprocess
from pathlib import Path
import _bootstrap
from scio_offline import research as r


if __name__=='__main__':
    p=argparse.ArgumentParser(); p.add_argument('--output',required=True); a=p.parse_args()
    spec=importlib.util.spec_from_file_location('public_safety', 'tools/check_public_safety.py')
    safety=importlib.util.module_from_spec(spec); spec.loader.exec_module(safety)
    names=set(subprocess.check_output(['git','diff','--name-only'],text=True).splitlines())
    names.update(subprocess.check_output(['git','ls-files','--others','--exclude-standard'],text=True).splitlines())
    outside=sorted(x for x in names if not x.startswith('dev/'))
    findings=[]; scanned=[]
    for name in sorted(names):
        path=Path(name)
        if not path.is_file(): continue
        raw=path.read_bytes()
        if name.endswith('.gz'):
            value=json.loads(gzip.decompress(raw))
            # The large repeated config table contains only hashes and enumerated
            # labels; validate its shape instead of rescanning 100 MB of repeats.
            for item in value.pop('configurations',[]):
                valid=(set(item)=={'key_sha256','config','stage'} and
                       re.fullmatch('[0-9a-f]{64}',item['key_sha256']) and
                       re.fullmatch('[A-Za-z0-9_-]+',item['stage']) and
                       len(item['config'])==4 and all(
                           isinstance(x,int) or (isinstance(x,str) and re.fullmatch('[A-Za-z0-9_-]+',x))
                           for x in item['config']))
                if not valid: findings.append({'file':name,'kind':'invalid configuration shape'})
            raw=json.dumps(value).encode()
        try: text=raw.decode('utf-8')
        except UnicodeDecodeError: continue
        scanned.append(name)
        for label,pattern in safety.PATTERNS.items():
            if pattern.search(text): findings.append({'file':name,'kind':label})
    directory=Path('dev/analysis_output/bounded_identity_20261004_run')
    raw=(directory/'manifest.json').read_bytes()
    packed=(directory/'manifest.json.gz').read_bytes()
    record=json.loads((directory/'manifest_digest.json').read_text())
    matches=(gzip.decompress(packed)==raw and r.sha(raw)==record['manifest_sha256']
             and r.sha(packed)==record['gzip_sha256'])
    r.write_new(a.output,{'changed_paths_outside_dev':outside,'scanned_paths':scanned,
                         'credential_or_path_findings':findings,'manifest_archive_matches':matches,
                         'passed':not outside and not findings and matches})
    print(json.dumps({'outside_dev':len(outside),'findings':len(findings),'manifest_matches':matches}))
    raise SystemExit(1 if outside or findings or not matches else 0)
