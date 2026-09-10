"""Import bootstrap for the offline-decoding research scripts.

They live one level below the repository root but address data with paths
relative to it ("01_rawdata/...", "dev/analysis_output/..."), and import ``scio`` from
``src/`` and ``scio_offline`` from ``dev/``. Importing this module first makes both work no matter where the
script is launched from.
"""

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

for _sub in ("src", "dev"):
    _p = str(ROOT / _sub)
    if _p not in sys.path:
        sys.path.insert(0, _p)

os.chdir(ROOT)
