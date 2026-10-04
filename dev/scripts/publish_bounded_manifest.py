"""Publish a deterministic compressed manifest and its portable digest."""
import argparse
import gzip
import json
from pathlib import Path
import _bootstrap
from scio_offline import bounded_campaign as c, research as r


if __name__=='__main__':
    p=argparse.ArgumentParser(); p.add_argument('directory'); a=p.parse_args()
    root=c.output_dir(a.directory)
    raw=(root/'manifest.json').read_bytes()
    packed=gzip.compress(raw,mtime=0)
    with (root/'manifest.json.gz').open('xb') as f: f.write(packed)
    manifest=json.loads(raw)
    r.write_new(root/'manifest_digest.json',{
        'manifest_sha256':r.sha(raw),'gzip_sha256':r.sha(packed),
        'manifest_bytes':len(raw),'gzip_bytes':len(packed),
        'configurations':len(manifest['configurations']),
        'unique_identity_keys':len(manifest['key_manifest']),
        'stage_counts':manifest['counts'],
        'purpose':'Lossless archive of full execution manifest; raw copy remains local for resumability.'})
