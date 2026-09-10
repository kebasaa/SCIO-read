#!/usr/bin/env python
"""Capture a labeled, repeatable SCIO series using read-only USB commands."""

from __future__ import annotations

import argparse
import time
from pathlib import Path

import _bootstrap  # noqa: F401  (sets sys.path + cwd to the repo root)

from scio import store  # noqa: E402
from scio.usb import ScioUSB, find_scio_ports  # noqa: E402


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--port", help="serial port; auto-selects a matching SCIO when omitted")
    ap.add_argument("--label", required=True, help="target label, e.g. static_target, dark, mirror")
    ap.add_argument("--count", type=int, default=30)
    ap.add_argument("--calibration", help="white-reference JSON associated with this series")
    ap.add_argument("--event", choices=("none", "repositioned", "reconnected", "rebooted"), default="none")
    ap.add_argument("--notes", default="")
    ap.add_argument("--interval", type=float, default=0.2)
    ap.add_argument("--output", default="01_rawdata/scan_json")
    args = ap.parse_args(argv)
    if args.count < 1:
        ap.error("--count must be positive")
    port = args.port
    if not port:
        candidates = [p for p in find_scio_ports() if p["is_scio"]]
        if len(candidates) != 1:
            ap.error("specify --port unless exactly one SCIO USB port is detected")
        port = candidates[0]["device"]
    with ScioUSB(port) as dev:
        device = dev.read_device_info()
        fw = int(device.get("firmware_version", 0))
        for i in range(args.count):
            temp = dev.read_temperature()
            captured = dev.sample_spectrum(fw)
            stamp = time.strftime("%Y%m%d_%H%M%S") + f"_{args.label}_{i + 1:03d}"
            path = store.save_scan(
                captured["blobs"], device, temp, captured["status_word"], args.calibration,
                out_dir=Path(args.output), stamp=stamp,
                extra_meta={"target_label": args.label, "replicate_index": i + 1,
                            "capture_event": args.event, "operator_notes": args.notes},
            )
            print(path)
            if i + 1 < args.count:
                time.sleep(args.interval)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
