"""Report only power-related complete SCIO frames in supplied Bluetooth logs."""
import argparse
from pathlib import Path
import _bootstrap
from scio_offline.snoop import extract
from scio_offline import research as r


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--apps', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    rows = []
    for path in sorted(a.apps.glob('btsnoop*')):
        raw = path.read_bytes()
        parsed = extract(raw)
        frames = []
        for msg in parsed['messages']:
            if msg['command'] not in (0x83, 0x9a, 0x9b):
                continue
            frames.append({'command': msg['command'], 'direction': msg['direction'],
                           'start_record': msg['start_record'], 'bytes': len(msg['data']),
                           'sha256': r.sha(msg['data']),
                           'first_four_bytes_hex': msg['data'][:4].hex()})
        rows.append({'source': path.name, 'sha256': r.sha(raw),
                     'parser_counts': parsed['counts'],
                     'complete_scio_frames': len(parsed['messages']), 'power_frames': frames})
    r.write_new(a.output, {'logs': rows, 'limits': 'Only complete reassembled frames for 0x83/0x9A/0x9B. Absence does not exclude support; capture duration, device state and missing traffic limit inference.'})
    print([(x['source'], len(x['power_frames'])) for x in rows])


if __name__ == '__main__':
    main()
