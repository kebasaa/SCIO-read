#!/usr/bin/env python
"""Download this SCiO's firmware + binning tables from the Consumer Physics server.

Run it yourself in an interactive terminal - it asks for your SCiO account email
and password via getpass; the password goes straight to auth.consumerphysics.com
and is never stored or printed.

    python download_firmware.py

It logs in, asks the server for an upgrade while reporting outdated versions, and
saves any returned blobs (dsp_op, dsp_boot, dsp_dec, centers, bins, ...) to
01_rawdata/device_files/ as *.bin. Then analyse with notebook 08 / recover_key.py.
"""

from __future__ import annotations

import getpass
import json
import sys
from pathlib import Path

import _bootstrap  # noqa: F401  (sets sys.path + cwd to the repo root)

from scio import cloud  # noqa: E402
from scio_offline import firmware  # noqa: E402

# This device (from 01_rawdata/device_files/). Override if you use another unit.
BLE_ID = "01665900004C99B4"
I2S_TAG = "20150812-e:PRODUCTION"
OUT_DIR = Path("01_rawdata/device_files")


def _arg(name: str):
    """Return the value of --name VALUE or --name=VALUE from argv, else None."""
    args = sys.argv[1:]
    for i, a in enumerate(args):
        if a == name and i + 1 < len(args):
            return args[i + 1]
        if a.startswith(name + "="):
            return a.split("=", 1)[1]
    return None


def main() -> int:
    redownload = "--redownload" in sys.argv[1:]
    token = _arg("--token")   # supply a bearer token to skip the login step

    # Reuse an existing raw backup so we never have to download twice.
    existing = sorted(OUT_DIR.glob(f"firmware_raw_{BLE_ID}_*.json"))
    if existing and not redownload:
        raw_path = existing[-1]
        print(f"Using existing backup (no login needed): {raw_path}")
        print("  (pass --redownload to fetch a fresh copy from the server.)\n")
        new_version = json.loads(raw_path.read_text(encoding="utf-8")).get("new_version") or {}
        return _process(new_version)

    if token:
        print(f"Using supplied bearer token ({len(token)} chars); skipping login.\n")
    else:
        print("SCiO firmware download - Consumer Physics account login")
        print(f"  device BLE id : {BLE_ID}")
        print(f"  i2s tag       : {I2S_TAG}\n")
        username = input("SCiO account email: ").strip()
        password = getpass.getpass("Password (hidden): ")
        try:
            token = cloud.login(username, password, debug="--debug" in sys.argv[1:])
        except cloud.CloudError as e:
            print(f"\nLogin failed: {e}")
            return 1
        print(f"Logged in. Token: {token[:6]}... ({len(token)} chars)\n")

    # Report all firmware versions as 0x00 so the server offers the full set.
    try:
        new_version = cloud.fetch_firmware(token, BLE_ID, I2S_TAG)
    except cloud.CloudError as e:
        print(f"firmware-upgrade request failed: {e}")
        return 1

    if not new_version:
        print("Server returned no new_version (nothing offered for these versions).")
        print("The device may be considered up to date. Try editing the reported")
        print("versions in scio/cloud.py (e.g. one below the real values).")
        return 1

    # Archive the RAW server response first (base64 blobs exactly as delivered),
    # timestamped and never overwritten, so this download never has to be repeated.
    import datetime as _dt
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    raw_path = OUT_DIR / f"firmware_raw_{BLE_ID}_{stamp}.json"
    raw_path.write_text(json.dumps(
        {"ble_id": BLE_ID, "i2s_tag": I2S_TAG, "fetched_at": stamp, "new_version": new_version},
        indent=1), encoding="utf-8")
    print(f"Raw backup saved: {raw_path}\n")

    return _process(new_version)


def _process(new_version: dict) -> int:
    """Decode the raw blobs to *.bin and triage them (shared by both paths)."""
    if not new_version:
        print("Backup contains no blobs. Delete it and re-run with --redownload.")
        return 1
    print("Files available:")
    for name, b64 in new_version.items():
        n = len(b64) if isinstance(b64, str) else 0
        print(f"  {name:20s} base64 {n} chars")

    written = cloud.save_firmware(new_version, OUT_DIR)
    print(f"\nDecoded {len(written)} file(s) to {OUT_DIR}:")
    for p in written:
        print(f"  {p.name:20s} {len(p.read_bytes()):7d} B")

    blobs = firmware.load_blob_dir(OUT_DIR)
    if blobs:
        print("\nTriage:")
        for name, t in firmware.triage(blobs).items():
            print(f"  {name:20s} {t['size']:7d} B  entropy {t['entropy']:.2f}  {t['verdict']}")
    print("\nNext: run 08_scio_keyrecovery.ipynb or:")
    print("  python recover_key.py --scans 01_rawdata/scan_json --firmware 01_rawdata/device_files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
