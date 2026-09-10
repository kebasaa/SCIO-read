#!/usr/bin/env python
"""Search AES/identifier hypotheses using repeated static SCIO captures."""

from __future__ import annotations

import argparse
import glob
import json
from pathlib import Path

import _bootstrap  # noqa: F401  (sets sys.path + cwd to the repo root)

from scio import corpus  # noqa: E402
from scio_offline.repeatability import search_identifier_keys  # noqa: E402


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--scans", default="01_rawdata/scan_json/*current_static*.json")
    ap.add_argument("--scope", choices=("single", "serial-pairs", "all"), default="single")
    ap.add_argument("--max-scans", type=int, default=6)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--output", default="analysis_output/key_repeatability_report.json")
    ap.add_argument("--serial-number", help="full device serial to add to key hypotheses")
    ap.add_argument("--case-serial", help="serial printed on the SCIO case")
    args = ap.parse_args(argv)
    records = [corpus.load_record(path) for path in sorted(glob.glob(args.scans))]
    extra_device = {"serial_number": args.serial_number, "case_serial": args.case_serial}
    report = search_identifier_keys(records, args.scope, args.max_scans, args.workers,
                                    extra_device=extra_device)
    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("scope", "scans", "unique_keys", "best", "conclusion")}, indent=2))
    return 0 if report["hits"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
