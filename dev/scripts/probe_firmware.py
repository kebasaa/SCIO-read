#!/usr/bin/env python
"""Log in once and try several version-claim strategies against firmware-upgrade.

The server returns new_version=null when it thinks the device is up to date. To
make it offer the blobs we must report versions it considers OUTDATED. This
probe logs in (getpass) and tries a handful of claim strategies back-to-back
(the token is short-lived), printing what each returns. Whatever yields files,
we fold into download_firmware.py.

    python probe_firmware.py
"""

from __future__ import annotations

import getpass
import json
import sys
from pathlib import Path

import _bootstrap  # noqa: F401  (sets sys.path + cwd to the repo root)

from scio import cloud  # noqa: E402

BLE_ID = "01665900004C99B4"
I2S = "20150812-e:PRODUCTION"

# key = file id in hex ; value = reported current version in hex.
# Real current versions on this unit: ble 0x7D(125), dsp_boot 0x11(17),
# dsp_dec 0x0C(12), dsp_op 0x93(147); tables (0x64-0x67) are version 3.
REAL = {"0x57": "0x7D", "0x5A": "0x11", "0x5B": "0x0C", "0x5C": "0x93"}
BELOW = {"0x57": "0x7C", "0x5A": "0x10", "0x5B": "0x0B", "0x5C": "0x92"}
ONES = {k: "0x01" for k in REAL}
ZERO = {k: "0x00" for k in REAL}
TABLES_BELOW = {"0x64": "0x02", "0x65": "0x02", "0x66": "0x02", "0x67": "0x02"}

STRATEGIES = [
    ("all one below real",        BELOW,                 I2S),
    ("all 0x01",                  ONES,                  I2S),
    ("dsp_op one below only",     {**REAL, "0x5C": "0x92"}, I2S),
    ("one below + tables below",  {**BELOW, **TABLES_BELOW}, I2S),
    ("one below, no i2s tag",     BELOW,                 None),
    ("real (baseline=up to date)", REAL,                 I2S),
    ("all 0x00 (already seen null)", ZERO,               I2S),
]


def main() -> int:
    username = input("SCiO account email: ").strip()
    password = getpass.getpass("Password (hidden): ")
    try:
        token = cloud.login(username, password)
    except cloud.CloudError as e:
        print(f"Login failed: {e}")
        return 1
    print(f"Logged in ({len(token)} char token). Trying strategies:\n")

    winner = None
    for label, versions, i2s in STRATEGIES:
        try:
            nv = cloud.fetch_firmware(token, BLE_ID, i2s, versions=versions)
        except cloud.CloudError as e:
            print(f"  {label:32s} ERROR {e}")
            # token may have expired; stop and let the user re-run
            if "401" in str(e) or "403" in str(e):
                print("  (token likely expired - re-run the probe)")
                break
            continue
        if nv:
            files = {k: (len(v) if isinstance(v, str) else v) for k, v in nv.items()}
            print(f"  {label:32s} OFFERED: {files}")
            if winner is None:
                winner = (label, versions, i2s, nv)
        else:
            print(f"  {label:32s} null (nothing offered)")

    if winner:
        label, versions, i2s, nv = winner
        out = Path("01_rawdata/device_files")
        out.mkdir(parents=True, exist_ok=True)
        import datetime
        stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        raw = out / f"firmware_raw_{BLE_ID}_{stamp}.json"
        raw.write_text(json.dumps({"ble_id": BLE_ID, "i2s_tag": i2s,
                                   "strategy": label, "new_version": nv}, indent=1))
        print(f"\nWINNER: '{label}' -> saved raw backup {raw}")
        print("Now run:  python download_firmware.py    (it will use this backup)")
    else:
        print("\nNo strategy produced files. Paste this output back.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
