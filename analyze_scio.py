#!/usr/bin/env python
"""Build a canonical SCIO corpus index and hypothesis-neutral evidence report."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from scio import corpus, evidence
from scio.image_hypothesis import image_hypothesis_report
from scio.stream_hypothesis import stream_hypothesis_report
from scio.reference import inspect_reference_csv, validate_spectral_ratio


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("roots", nargs="*", default=["01_rawdata/log_extracted", "01_rawdata/scan_json",
                                                  "01_rawdata/scan_json_calibration"],
                    help="JSON files/directories to inventory")
    ap.add_argument("--old-scans", help="optional local archive such as ../__scio/scan_json_old")
    ap.add_argument("--output", default="analysis_output", help="derived-output directory")
    args = ap.parse_args(argv)
    roots = list(args.roots) + ([args.old_scans] if args.old_scans else [])
    records, errors = corpus.build_corpus(roots)
    out = Path(args.output)
    index_path = corpus.write_index(records, out / "corpus_index.json", errors)
    report = evidence.corpus_report(records)
    report["corpus_errors"] = errors
    report["image_hypothesis"] = image_hypothesis_report(records)
    static_records = [record for record in records if record.label == "current_static"]
    if static_records:
        report["stream_hypothesis"] = stream_hypothesis_report(static_records)
    reference_paths = [Path("01_rawdata/app_researcher_output/scan.csv"),
                       Path("01_rawdata/app_researcher_output/SCIO_scans_from_tech_support.csv")]
    report["reference_tables"] = []
    for path in reference_paths:
        if path.exists():
            ref = inspect_reference_csv(path)
            report["reference_tables"].append({
                "path": ref.path, "header_row_zero_based": ref.header_row, "rows": ref.rows,
                "metadata_columns": ref.metadata_columns,
                "axes": {name: {"count": len(axis), "start": min(axis), "stop": max(axis)}
                         for name, axis in ref.axes.items()},
                "spectral_ratio_validation": validate_spectral_ratio(path),
            })
    evidence_path = evidence.write_report(report, out / "transform_evidence_report.json")
    print(json.dumps({"records": len(records), "errors": len(errors),
                      "index": str(index_path), "evidence": str(evidence_path),
                      "status": report["interpretation"]["status"]}, indent=2))
    return 0 if records else 2


if __name__ == "__main__":
    raise SystemExit(main())
