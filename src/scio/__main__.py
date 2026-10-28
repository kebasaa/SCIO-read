"""Command line: ``python -m scio contribute`` / ``python -m scio import``.

    python -m scio contribute --name "closed cap" --count 5          # USB, first SCiO port
    python -m scio contribute --name wood --count 3 --ble            # Bluetooth LE
    python -m scio import scio_contrib_<device_id>_<stamp>.zip      # owner side

See :mod:`scio.contribute` for what a bundle contains and why.
"""

from __future__ import annotations

import argparse
import json
import sys


def _open_device(args):
    if args.ble is not None:
        from .ble import ScioBLE
        return ScioBLE(args.ble or None)
    from .usb import ScioUSB, find_scio_ports
    port = args.port
    if port is None:
        found = [p for p in find_scio_ports() if p["is_scio"]]
        if not found:
            sys.exit("no SCiO USB port found; plug it in (power-cycle it if it stays silent) "
                     "or pass --port / --ble")
        port = found[0]["device"]
    return ScioUSB(port)


def _enter(prompt: str) -> bool:
    try:
        input(prompt)
    except EOFError:
        return False
    return True


def _contribute(args) -> None:
    from . import contribute

    def white_prompt(report):
        print(f"\nWhite reference needed ({report['status']}).")
        return _enter("Put the closed white cover on the SCiO, then press Enter (Ctrl+C aborts)... ")

    def scan_prompt(i):
        if args.no_prompt:
            return True
        return _enter(f"\nScan {i}/{args.count}: place the SCiO on '{args.name}', then press Enter... ")

    with _open_device(args) as dev:
        path = contribute.capture_bundle(dev, args.name, args.count, args.out, comment=args.comment,
                                         on_calibration_needed=white_prompt, before_scan=scan_prompt)
    print(f"\nDone. Send this file: {path}")


def _import(args) -> None:
    from . import contribute
    for zip_path in args.bundle:
        print(json.dumps(contribute.import_bundle(zip_path), indent=1))
    print("Replay with session.process_pending(pause=20) when online.")


def main(argv=None) -> None:
    p = argparse.ArgumentParser(prog="python -m scio")
    sub = p.add_subparsers(dest="command", required=True)

    c = sub.add_parser("contribute", help="capture scans + white reference + device identity into a zip")
    c.add_argument("--name", required=True, help="what is being scanned, e.g. 'closed cap'")
    c.add_argument("--count", type=int, default=1, help="number of scans of this target")
    c.add_argument("--comment", default="", help="free text stored with each scan")
    c.add_argument("--out", default=".", help="folder for the bundle (default: current folder)")
    c.add_argument("--port", help="USB serial port (default: the first SCiO found)")
    c.add_argument("--ble", nargs="?", const="", default=None,
                   help="use Bluetooth LE; optionally a device name or address")
    c.add_argument("--no-prompt", action="store_true", help="do not wait for Enter between scans")
    c.set_defaults(func=_contribute)

    i = sub.add_parser("import", help="copy contributor bundles into 01_rawdata (append-only)")
    i.add_argument("bundle", nargs="+", help="scio_contrib_*.zip")
    i.set_defaults(func=_import)

    args = p.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
