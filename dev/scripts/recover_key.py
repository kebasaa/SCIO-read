#!/usr/bin/env python
"""Test bounded SCIO AES/key hypotheses against local captures.

Usage:
    python recover_key.py --scans 01_rawdata/scan_json --firmware 01_rawdata/device_files
    python recover_key.py --scans 01_rawdata/log_extracted   # fixtures, no firmware

Without --firmware it tests observed identifiers, serials and version fields.
Neither AES nor any derivation is presumed; smoothness-only hits are candidates,
not recovered keys, until held-out spectral validation succeeds.
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import sys

import _bootstrap  # noqa: F401  (sets sys.path + cwd to the repo root)

from scio import store  # noqa: E402
from scio_offline import firmware, keyrecover  # noqa: E402


def _load_scans(paths):
    scans = []
    for p in paths:
        if os.path.isdir(p):
            files = sorted(glob.glob(os.path.join(p, "*.json"))) + \
                sorted(glob.glob(os.path.join(p, "*", "*.json")))
        else:
            files = [p]
        for f in files:
            try:
                if "log_extracted" in f:
                    scans.append(store.load_fixture(f))
                else:
                    scans.append(store.load_scan(f))
            except Exception as e:  # noqa: BLE001
                print(f"  skip {f}: {e}", file=sys.stderr)
    return scans


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--scans", nargs="+", required=True, help="scan file(s) or directory(ies)")
    ap.add_argument("--firmware", help="directory of extracted firmware blobs (*.bin)")
    ap.add_argument("--threshold", type=float, default=0.6, help="oracle score to call a hit")
    ap.add_argument("--serial", help="serial number printed on the unit (hypothesis input)")
    ap.add_argument("--device-id", help="override/add device ID hypothesis input")
    ap.add_argument("--sensor-id", help="override/add Aptina/sensor ID hypothesis input")
    ap.add_argument("--ble-id", help="override/add BLE ID hypothesis input")
    ap.add_argument("--json", action="store_true", help="print the full result as JSON")
    ap.add_argument("--workers", type=int, default=min(8, os.cpu_count() or 1),
                    help="parallel candidate checks (default: up to 8)")
    args = ap.parse_args(argv)

    scans = _load_scans(args.scans)
    print(f"Loaded {len(scans)} scan file(s).")
    if not scans:
        return 2

    fw = None
    if args.firmware:
        fw = firmware.load_blob_dir(args.firmware)
        print(f"Loaded firmware blobs: {sorted(fw)}" if fw else "No firmware blobs found in that directory.")

    # Merge metadata across captures so older records can contribute serial or
    # sensor fields absent from newer capture schemas.
    device = {}
    for scan in scans:
        for key, value in scan.get("device", {}).items():
            if value not in (None, ""):
                device.setdefault(key, value)
    for field, value in (("serial_number", args.serial), ("device_id", args.device_id),
                         ("sensor_id", args.sensor_id), ("ble_id", args.ble_id)):
        if value:
            device[field] = value
    res = keyrecover.recover(scans, firmware_blobs=fw, device=device,
                             score_threshold=args.threshold, workers=max(1, args.workers))

    if args.json:
        print(json.dumps({
            "signatures": res.signatures,
            "firmware_triage": res.firmware_triage,
            "n_candidates": res.n_candidates,
            "n_derivations": res.n_derivations,
            "best": res.best,
            "hits": res.hits[:5],
            "conclusion": res.conclusion,
        }, indent=2, default=str))
        return 0

    if res.firmware_triage:
        print("\nFirmware triage:")
        for name, t in res.firmware_triage.items():
            print(f"  {name:18s} {t['size']:>7d} B  entropy {t['entropy']:.2f}  {t['verdict']}")
    if res.signatures:
        print("\nCipher signatures found in firmware:")
        for name, offs in res.signatures.items():
            print(f"  {name:16s} at {['0x%X' % o for o in offs[:4]]}")
    print(f"\nTried {res.n_candidates} unique candidate key(s) "
          f"from {res.n_derivations} named derivation(s).")
    if res.best:
        print(f"Best oracle score: {res.best['score']:.3f} "
              f"({res.best['label']}, {res.best['mode']}/{res.best['iv']}, view {res.best['view']})")
    print("\n=> " + res.conclusion)
    return 0 if res.hits else 1


if __name__ == "__main__":
    raise SystemExit(main())
