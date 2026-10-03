#!/usr/bin/env python
"""Compatibility entry point for the corrected dark-frame search.

Historical results remain in analysis_output. The previous implementation mixed
headers into ciphertext and is not valid evidence excluding identifier keys.
Use --output dev/analysis_output/<fresh-run>.json; optional --extended/--foreign.
"""
import _bootstrap
from rescreen_v2 import main

if __name__ == "__main__":
    main()
