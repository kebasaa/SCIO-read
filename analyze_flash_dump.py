#!/usr/bin/env python
"""Analyze repeat SPI/JTAG dumps and extract only strongly validated SCIO files."""
import argparse, json
from pathlib import Path
from scio.flashdump import analyze_dump, compare_dumps, extract_strong

def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("dumps", nargs="+", help="two independently read dumps are strongly recommended")
    ap.add_argument("--output", default="analysis_output/flash_dump_report.json")
    ap.add_argument("--extract-dir", help="extract unique strong candidates here")
    ap.add_argument("--no-rolling-sum", action="store_true", help="skip weak whole-dump byte-sum scan")
    args = ap.parse_args(argv)
    reports = [analyze_dump(p, not args.no_rolling_sum) for p in args.dumps]
    result = {"schema": "scio-flash-dump-set/1", "comparison": compare_dumps(args.dumps), "dumps": reports}
    if args.extract_dir:
        result["extracted"] = extract_strong(reports[0], args.dumps[0], args.extract_dir)
    path = Path(args.output); path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps({"comparison": result["comparison"],
                      "strong_candidates": [r["strong_candidates"] for r in reports],
                      "report": str(path)}, indent=2))
    return 0 if result["comparison"]["identical"] and any(r["strong_candidates"] for r in reports) else 1

if __name__ == "__main__":
    raise SystemExit(main())
