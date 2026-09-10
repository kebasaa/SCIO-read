"""Make the two source trees importable without installing anything.

``src/``  -> ``scio``          the working capture/upload pipeline (strand A)
``dev/``  -> ``scio_offline``  unresolved offline-decoding research (strand B)

Keeping them in separate trees is deliberate: ``pytest tests/`` must pass with
``dev/`` absent, which is what proves the two strands are decoupled.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
for sub in ("src", "dev"):
    path = ROOT / sub
    if path.is_dir() and str(path) not in sys.path:
        sys.path.insert(0, str(path))
