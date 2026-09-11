#!/usr/bin/env python
"""Turn captured raw SCiO scans into spectra via the Consumer Physics cloud.

With an active SCiO account, the server still computes the 331-point reflectance
spectrum from the raw blobs - exactly what the app did. This logs in (getpass),
sends each captured scan together with the stored white reference, and saves the
returned spectrum as JSON + CSV (and a PNG) under 02_processed_data/spectra/.

    python analyze_scan.py                 # all scans in 01_rawdata/scan_json
    python analyze_scan.py --scan 01_rawdata/scan_json/scan_20260907_hand.json
    python analyze_scan.py --debug         # show the login redirect chain

The token is short-lived, so login and all requests happen back-to-back.
"""

from __future__ import annotations

import glob
import json
import sys
from pathlib import Path

import _bootstrap  # noqa: F401  (sets sys.path + cwd to the repo root)

from scio import cloud, credentials, store  # noqa: E402

OUT_DIR = Path("02_processed_data/spectra")


def _arg(name):
    a = sys.argv[1:]
    for i, x in enumerate(a):
        if x == name and i + 1 < len(a):
            return a[i + 1]
        if x.startswith(name + "="):
            return x.split("=", 1)[1]
    return None


def main() -> int:
    one = _arg("--scan")
    if one:
        scan_files = [one]
    else:
        scan_files = sorted(glob.glob("01_rawdata/scan_json/scan_*.json"))
    if not scan_files:
        print("No scans found in 01_rawdata/scan_json/.")
        return 2

    # Load scans and the white reference for the device (skip old-format files).
    scans = []
    for f in scan_files:
        try:
            sc = store.load_scan(f)
            if "sample" in sc.get("blobs", {}):
                scans.append(sc)
            else:
                print(f"  skip {Path(f).name}: no sample blob")
        except Exception as e:
            print(f"  skip {Path(f).name}: {e}")
    if not scans:
        print("No loadable new-format scans. Capture with 01_scio_scan_to_spectrum.ipynb first.")
        return 2
    device = scans[0]["device"]
    device_id = device["device_id"]
    i2s = device.get("i2s_tag_config")
    white = store.load_latest_calibration(device_id)
    if not white:
        print("No white reference found in 01_rawdata/scan_json_calibration/.")
        return 2
    print(f"{len(scans)} scan(s); device {device_id}; white ref {Path(white['path']).name}")

    try:
        token = credentials.get_token(force_prompt="--relogin" in sys.argv[1:],
                                      debug="--debug" in sys.argv[1:])
    except cloud.CloudError as e:
        print(f"Login failed: {e}")
        return 1
    print(f"Logged in ({len(token)} char token). Sending scans...\n")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    ok = 0
    for sc in scans:
        name = Path(sc["path"]).stem
        payload = cloud.build_scan_payload(sc, white, device_id, i2s)
        try:
            resp = cloud.analyze_scan(token, payload)
            wl, refl = cloud.spectrum_from_response(resp)
        except cloud.CloudError as e:
            print(f"  {name:28s} FAILED: {e}")
            if "401" in str(e) or "403" in str(e):
                print("  (token expired - re-run to finish the rest)")
                break
            continue
        lo, hi = min(refl), max(refl)
        print(f"  {name:28s} OK: {len(refl)} points, {wl[0]}-{wl[-1]} nm, range [{lo:.4f}, {hi:.4f}]")
        # Full record: links to the raw inputs + the exact payload sent + the
        # complete server response + parsed spectrum. Everything needed to later
        # reverse-engineer the raw->spectrum transform offline.
        payload_meta = {k: v for k, v in payload.items()
                        if k not in ("sample", "sample_dark", "sample_gradient",
                                     "sample_white", "sample_white_dark", "sample_white_gradient")}
        out = OUT_DIR / f"{name}_spectrum.json"
        out.write_text(json.dumps({
            "schema": "scio-spectrum/2",
            "scan_file": store.portable_path(sc["path"]),
            "calibration_file": store.portable_path(white["path"]),
            "request_meta": payload_meta,
            "response": resp,                      # full server response, verbatim
            "wavelength_nm": wl, "reflectance": refl,
        }, indent=1))
        ok += 1

    print(f"\nSaved {ok} spectrum file(s) to {OUT_DIR}.")
    if ok:
        print("Plot with: import json; d = json.load(open(<file>)); "
              "plt.plot(d['wavelength_nm'], d['reflectance'])")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
