"""Ingest the contributed fw-138 scans as canonical records, then replay them.

Reads the committed device specs + blobs
(`analysis_output/foreign_fw138_20261008/{device,scans}.json`) and writes canonical
`scio-scan/2` records for the contributed second unit: the white reference into
`01_rawdata/scan_json_calibration/`, and the three samples (pine/tomato/skin) into
`01_rawdata/scans/`, each embedding that white. Append-only — only new files.

With `--process` it then calls `session.process_pending(pause=20)`, which sends each new
record to the server (his device_id + bare `20150812:PRODUCTION` tag + his white) and
writes the returned fw-138 spectra into `02_processed_data/`. All blobs are his under his
own identity, so the device-bound signature is satisfied.

    python dev/scripts/ingest_foreign_fw138.py            # build records only
    python dev/scripts/ingest_foreign_fw138.py --process  # build + replay on the server
"""
import argparse
import base64
import json
from pathlib import Path

import _bootstrap  # noqa: F401
from scio import session, store
from scio.paths import portable_path
from scio_offline import research as r

RUN = r.DEV / 'analysis_output' / 'foreign_fw138_20261008'
SLUG = 'fw138_contrib'


def _bytes(b64_map):
    return {k: base64.b64decode(v) for k, v in b64_map.items()}


def build_records(run_dir=RUN, wr_dir=None, scans_dir=None, slug=SLUG, reuse_white=False):
    device_specs = json.loads((run_dir / 'device.json').read_text())['device']
    scans = json.loads((run_dir / 'scans.json').read_text())
    device = {k: device_specs[k] for k in device_specs}        # all device specs
    device['i2s_tag_config'] = scans['i2s_tag_config']
    device['firmware_version'] = scans['firmware_version']
    wr_dir = wr_dir or store.WR_DIR

    wr = scans['white_reference']
    if reuse_white:
        wr_path = store.latest_calibration_path(device['device_id'], wr_dir)
        if wr_path is None:
            raise ValueError('reuse_white set but no existing calibration for this device')
        cal = store.load_scan(wr_path)
    else:
        wr_path = store.save_calibration(_bytes(wr['blobs_b64']), device,
                                         temp_before=wr['temperature'] or {}, temp_after=wr['temperature'] or {},
                                         out_dir=wr_dir, transport='usb')
        cal = store.load_latest_calibration(device['device_id'], wr_dir) or store.load_scan(wr_path)
    white_section = session._white_section(cal, portable_path(wr_path))

    written = []
    for i, s in enumerate(scans['samples'], 1):
        t = s.get('temperature') or {}
        rec = session.build_record(
            session.annotate(f"{slug} {s['material']}", f"{slug}-{i}",
                             "contributed second unit, fw-138"),
            device, _bytes(s['blobs_b64']), white_section,
            temperature={'scan_before': t, 'scan_after': t}, status_word=0,
            calibration={'status_at_scan': 'NO_NEED', 'thresholds': None,
                         'thresholds_source': 'not applicable (contributed unit)', 'report': None},
            transport='usb',
            provenance={'source': 'contributed second unit, fw-138', 'material': s['material'],
                        'notes': ['Captured on a different owner\'s fw-138 unit (older generation, '
                                  'bare 20150812 tag, 1416 B gradient).',
                                  'Timestamps are the ingestion time, not the original capture time.']})
        written.append(session.write_record(rec, out_dir=scans_dir or session.SCANS_DIR))
    return wr_path, written


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--process', action='store_true', help='also replay on the server (pause=20)')
    a = p.parse_args()
    existing = sorted((r.ROOT / 'tmp_unused').parent.glob(f'01_rawdata/scans/*{SLUG}*.json'))
    if existing:
        print(f'records already present ({len(existing)}); skipping build.')
        for w in existing:
            print('record:', portable_path(w))
    else:
        wr_path, written = build_records()
        print('white reference:', portable_path(wr_path))
        for w in written:
            print('record:', portable_path(w))
    if not a.process:
        print('\nbuilt records only; pass --process to fetch spectra from the server.')
        return
    results = session.process_pending(pause=20)
    mine = [row for row in results if SLUG in (row.get('scan') or '')]
    import numpy as np
    specs = {}
    for row in mine:
        print('processed:', row['scan'], '->', 'OK' if not row['error'] else f"ERROR {row['error']}")
        if row['processed']:
            d = json.loads(Path(r.ROOT / row['processed']).read_text())
            specs[row['scan']] = d['spectrum']['reflectance']
    distinct = len({tuple(round(x, 6) for x in v) for v in specs.values()})
    summary = {'processed': len(mine), 'with_spectrum': len(specs),
               'distinct_spectra': distinct,
               'all_331_finite': all(len(v) == 331 and np.isfinite(v).all() for v in specs.values())}
    r.write_new(RUN / 'replay_summary.json', summary)
    print(json.dumps(summary))


if __name__ == '__main__':
    main()
