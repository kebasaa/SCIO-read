"""Record size-only layout constraints (12 receptors, 331 bands), offline.

    python dev/scripts/analyze_size_constraints.py --output dev/analysis_output/<new-run>/size_constraints.json
"""
import argparse
from pathlib import Path

import _bootstrap  # noqa: F401
from scio_offline import research
from scio_offline import size_constraints as s


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    data = s.report()
    data["schema"] = "scio-size-constraints/1"
    data["sources"] = {"tables_and_firmware": "READ_FILE_HEADER on the fw-147 unit (README section 5)",
                       "bodies": "canonical scans (-e) and vendor fixtures (-o)",
                       "receptors": "SparkFun teardown: 12 filtered receptors"}
    data["observations"] = [
        "No table or body size is a whole number of 331 entries at any tested prefix/width: the "
        "tables are not plain per-band arrays.",
        "centers (96 B) is the only table with a clean 12-way split at zero prefix (12 x 8 B); "
        "consistent with one record per receptor, not evidence of it.",
        "No body splits 12 ways at 2-byte or wider width, and none fits 12-bit packing; equal "
        "per-receptor u16 sub-images are excluded for the plaintext-as-stored hypothesis.",
        "All bodies are multiples of 16 B; the -e/-o gradient difference is 240 B = 15 blocks = 12 x 20 B.",
    ]
    data["limits"] = "Size arithmetic only. A fit is not a layout; unequal splits and coded bodies are untouched."
    research.write_new(a.output, data)
    print("\n".join(data["observations"]))


if __name__ == "__main__":
    main()
