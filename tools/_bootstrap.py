"""Import bootstrap for the repository scripts.

They live one level below the repository root but address data with paths
relative to it ("01_rawdata/...", "02_processed_data/..."), and import ``scio`` from
``src/``. Importing this module first makes both work no matter where the
script is launched from.
"""

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

for _sub in ("src",):
    _p = str(ROOT / _sub)
    if _p not in sys.path:
        sys.path.insert(0, _p)

os.chdir(ROOT)
