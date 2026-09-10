#!/usr/bin/env python
"""Test bounded TEA/XTEA identifier-key hypotheses on static captures."""
import argparse, glob, json
from pathlib import Path
import _bootstrap  # noqa: F401  (sets sys.path + cwd to the repo root)

from scio import corpus  # noqa: E402
from scio_offline.embedded_cipher_hypothesis import search_embedded_ciphers  # noqa: E402

def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--scans", default="01_rawdata/scan_json/*current_static*.json")
    ap.add_argument("--max-scans", type=int, default=6)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--serial-number")
    ap.add_argument("--case-serial")
    ap.add_argument("--output", default="analysis_output/embedded_cipher_report.json")
    args = ap.parse_args(argv)
    records = [corpus.load_record(p) for p in sorted(glob.glob(args.scans))]
    report = search_embedded_ciphers(records, args.max_scans, args.workers,
        {"serial_number": args.serial_number, "case_serial": args.case_serial})
    path = Path(args.output); path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("scans", "unique_keys", "best", "conclusion")}, indent=2))
    return 0 if report["hits"] else 1

if __name__ == "__main__":
    raise SystemExit(main())
