"""Ingest the contributor's fw-138 re-takes and replay each attempt individually.

Builds the 4 re-take samples (2x tomato cut-flesh, 2x pine) as canonical records reusing the
existing fw-138 white calibration (the re-take white is byte-identical), then processes each
record on its own (not process_pending, so the old failed records are untouched). An owner
known-scan control runs first. Writes retake_summary.json with per-attempt outcomes. Deletion of
failures / superseded records is a separate manual step after reviewing the summary.

    python dev/scripts/ingest_foreign_fw138_retake.py [--process]
"""
import argparse
import json
import time
from pathlib import Path

import numpy as np

import _bootstrap  # noqa: F401
from scio import cloud, credentials, session
from scio.paths import portable_path
from scio_offline import research as r
from ingest_foreign_fw138 import build_records

RETAKE = r.DEV / 'analysis_output' / 'foreign_fw138_retake_20261008'
SLUG = 'fw138_retake'
OWN = r.DEV / 'analysis_output/recovery_20261003/oracle_network/00'


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--process', action='store_true')
    a = p.parse_args()

    existing = sorted((r.ROOT).glob(f'01_rawdata/scans/*{SLUG}*.json'))
    if existing:
        written = existing
        print(f'records already present ({len(existing)}); skipping build.')
    else:
        _, written = build_records(run_dir=RETAKE, slug=SLUG, reuse_white=True)
    for w in written:
        print('record:', portable_path(w))
    if not a.process:
        print('\nbuilt only; pass --process to replay on the server.')
        return

    token = credentials.get_token(prompt_if_needed=False)
    # control: a known owner scan must still return its spectrum (endpoint health)
    creq = json.loads((OWN.parent / '00_request.json').read_text())
    cresp = json.loads((OWN.parent / '00_response.json').read_text())
    _, cspec = cloud.spectrum_from_response(cloud.analyze_scan(token, creq['payload']))
    control_ok = bool(np.allclose(cspec, cresp['spectrum'], atol=1e-6, rtol=1e-6))
    print('control_ok:', control_ok)

    results = []
    for path in written:
        rec = session.load_record(path)
        name = (rec.get('annotation') or {}).get('name')
        time.sleep(20)
        row = {'record': portable_path(path), 'material': rec['provenance'].get('material')}
        try:
            out = session.process(path, token)
            d = json.loads(Path(out).read_text())
            spec = d['spectrum']['reflectance']
            row.update(status=200, processed=portable_path(out), n=len(spec),
                       finite_331=bool(len(spec) == 331 and np.isfinite(spec).all()),
                       reflectance_range=[float(np.min(spec)), float(np.max(spec))])
        except cloud.CloudError as exc:
            row.update(status='error', error=str(exc)[:160])
        results.append(row)
        print(row['material'], row.get('status'), row.get('reflectance_range'))

    ok = [x for x in results if x.get('finite_331')]
    r.write_new(RETAKE / 'retake_summary.json', {
        'control_ok': control_ok, 'results': results,
        'decoded': [x['material'] for x in ok],
        'failed': [x['material'] for x in results if not x.get('finite_331')],
        'distinct_spectra': len({tuple(round(y, 6) for y in json.loads(Path(r.ROOT / x['processed']).read_text())['spectrum']['reflectance']) for x in ok})})
    print('decoded:', [x['material'] for x in ok])


if __name__ == '__main__':
    main()
