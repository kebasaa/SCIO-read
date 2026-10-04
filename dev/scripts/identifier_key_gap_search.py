#!/usr/bin/env python
"""Run the identifier-key gap search (TEA/XTEA pairs + MAC, and non-AES ciphers).

Offline, read-only. Captures in, JSON report out under dev/analysis_output/.
These identity values are injected because the capture records only carry the
8-byte Aptina half and no MAC; they are this unit's known constants (0x01 reply
and the 2023 app log, README section 3), not guesses:

    aptina_full   00008e4c3832e1c8328045ab1161f198   (0x01 [8:24])
    aptina_upper  00008e4c3832e1c8                   (0x01 [8:16], never parsed before)
    aptinaId      00004c8e3238c8e18032ab45611198f1   (2023 app log, word-swapped)
    serial_prefix CPPCA0031C6PF0516009W6404386A1     (0x84 [10:40])
    serial_number CPPCA0031C6PF0516009W6404386A1DF1816004A
    address       B4:99:4C:59:66:01                  (BLE MAC)

Usage:
    python dev/scripts/identifier_key_gap_search.py --dry-run
    python dev/scripts/identifier_key_gap_search.py
"""

import argparse
import glob
import json
from pathlib import Path

import _bootstrap  # noqa: F401  (sets sys.path + cwd to the repo root)
from scio import corpus  # noqa: E402
from scio_offline import cipher_gap  # noqa: E402

KNOWN_IDENTITY = {
    "aptina_full": "00008e4c3832e1c8328045ab1161f198",
    "aptina_upper": "00008e4c3832e1c8",
    "aptinaId": "00004c8e3238c8e18032ab45611198f1",
    "serial_prefix": "CPPCA0031C6PF0516009W6404386A1",
    "serial_number": "CPPCA0031C6PF0516009W6404386A1DF1816004A",
    "address": "B4:99:4C:59:66:01",
}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--scans", default="01_rawdata/scan_json/*current_static*.json")
    ap.add_argument("--max-scans", type=int, default=6)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--dry-run", action="store_true", help="count configurations and exit")
    ap.add_argument("--output", default="dev/analysis_output/identifier_key_gap_20261004/identifier_key_gap.json")
    args = ap.parse_args(argv)

    paths = sorted(glob.glob(args.scans))
    if not paths:
        raise SystemExit(f"no captures matched {args.scans}")
    records = [corpus.load_record(p) for p in paths]
    for record in records:
        record.device.update({k: v for k, v in KNOWN_IDENTITY.items()
                              if not record.device.get(k)})

    if args.dry_run:
        info = cipher_gap.search(records, max_scans=args.max_scans, dry_run=True)
        info["known_identity_injected"] = sorted(KNOWN_IDENTITY)
        print(json.dumps(info, indent=2))
        return 0

    report = cipher_gap.search(records, max_scans=args.max_scans, workers=args.workers)
    report["scan_paths"] = [corpus.portable(p) if hasattr(corpus, "portable") else p for p in paths[:args.max_scans]]
    report["known_identity_injected"] = KNOWN_IDENTITY
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("unique_keys", "ciphers", "scans", "conclusion")}, indent=2))
    print("hits:", len(report["hits"]), "| random-control max:", round(report["random_controls"]["max"], 4))
    print("top:", report["top_candidates"][0]["repeatability"] if report["top_candidates"] else None,
          "->", report["top_candidates"][0]["labels"][:2] if report["top_candidates"] else None)
    print("wrote", out)
    return 0 if report["hits"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
