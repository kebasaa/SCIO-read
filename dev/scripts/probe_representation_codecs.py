"""Explore reversible byte representations without using held-out blob contents."""
import argparse
import json
from pathlib import Path
import numpy as np
import _bootstrap
from scio import session
from scio_offline import research as r
from scio_offline.representation_codecs import probe


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    manifest = json.loads((r.DEV/'analysis_output/recovery_20261003/corpus_final.json').read_text())
    confirmation = set(manifest['confirmation_ids'])
    candidates, protected = {}, set()
    for path in sorted((r.ROOT/'01_rawdata/scans').glob('*.json')):
        record = session.load_record(path)
        sample, white = session.record_blobs(record)
        blobs = {**sample, **white}
        identity = r.sha(b''.join(k.encode() + v for k,v in sorted(blobs.items())))
        for role, blob in blobs.items():
            digest = r.sha(blob)
            if identity in confirmation:
                protected.add(digest)
            candidates.setdefault(digest, {'data':blob,'occurrences':[]})['occurrences'].append(
                {'source':r.label(path), 'role':role, 'record_id':identity})
    results = []
    for digest, item in candidates.items():
        if digest in protected:
            continue  # Includes shared calibration blobs: do not tune on them.
        data = item['data']
        if len(data) < 8:
            raise ValueError('short blob')
        result = probe(data[8:])
        results.append({'blob_sha256':digest, 'body_bytes':len(data)-8,
                        'occurrences':item['occurrences'], **result})
    rng = np.random.default_rng(20261003)
    lengths = sorted({x['body_bytes'] for x in results})
    controls = [{'body_bytes':size, **probe(rng.bytes(size))}
                for size in lengths for _ in range(32)]
    report = {'cipher_step':None, 'protected_blob_count':len(protected),
              'exploratory_blob_count':len(results), 'offsets':list(range(33)),
              'observations':results, 'random_controls':controls,
              'actual_configurations':sum(x['unique_configurations'] for x in results),
              'limits':'Bounded representation/standard-codec probe; no proprietary format claim. Protected record hashes and shared blobs excluded; fresh captures and foreign samples not used. Stream completion alone is not intermediate or spectral validation. Fixed containers may include trailing bytes.'}
    r.write_new(a.output, report)
    print('exploratory blobs',len(results),'protected blobs',len(protected),
          'configurations',report['actual_configurations'],
          'complete streams',sum(len(x['complete_streams']) for x in results),
          'control streams',sum(len(x['complete_streams']) for x in controls))


if __name__ == '__main__':
    main()
