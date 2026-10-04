"""Map 0x88/0x89/0x93/0x95 and restore the zeroed BLE-ID fields, one write per run.

Background (README section 3): since 2026-09-07 this unit's READ_BLE_ID reply has
bytes [10:40] (serial prefix) and [66:130] (i2s tag) zeroed, most likely by the
empty-payload reserved-opcode sweep. No app sends these opcodes, so their meaning
is found by experiment: write a known ASCII value (the 0x91 rename format - raw,
no padding, no NUL) and see which bytes of the record change.

Usage (Bluetooth LE; press the device button first):

    python dev/scripts/restore_ble_id_record.py --snapshot --label baseline
    python dev/scripts/restore_ble_id_record.py --write 0x93 --value i2s --yes

Every run writes new files to 01_rawdata/probe_logs/ (append-only): the snapshot
before, the write request/reply, the snapshot after and a diff. A write that
changes anything outside the BLE-ID record, or gets an unexpected reply, is
reported as STOP. Reset, FILE_DOWNLOAD and empty payloads are never sent.
"""

import argparse
import json
import struct
import sys
from datetime import datetime

import _bootstrap  # noqa: F401
from scio import ble, protocol
from scio.protocol import Cmd, ScioTimeout

LOG_DIR = _bootstrap.ROOT / "01_rawdata" / "probe_logs"
CANDIDATES = {0x88, 0x89, 0x93, 0x95}
VALUES = {
    "i2s": b"20150812-e:PRODUCTION",
    "serial_a": b"CPPCA0031C6PF0516009W6404386A1",
    "serial_b": b"DF1816004A",
    "serial": b"CPPCA0031C6PF0516009W6404386A1DF1816004A",
}
REGIONS = {"ble_id": (0, 8), "ble_fw": (8, 10), "serial_a": (10, 40), "serial_b": (40, 50),
           "name": (50, 66), "i2s": (66, 130)}
FILE_IDS = (87, 89, 90, 91, 92, 99, 100, 101, 102, 103)


def _raw(dev, cmd, payload=b""):
    r = dev._command(cmd, payload)
    return {"command": r.command, "length": r.length, "hex": r.data.hex()}


def snapshot(dev) -> dict:
    snap = {"taken_at": datetime.now().astimezone().isoformat(timespec="seconds")}
    snap["ble_id"] = _raw(dev, Cmd.READ_BLE_ID)
    snap["device_id"] = _raw(dev, Cmd.READ_DEVICE_ID)
    snap["read_ble"] = _raw(dev, Cmd.READ_BLE)
    snap["file_list"] = _raw(dev, Cmd.READ_FILE_LIST)
    snap["file_headers"] = {str(f): _raw(dev, Cmd.READ_FILE_HEADER, struct.pack("<I", f))
                            for f in FILE_IDS}
    snap["battery"] = protocol.parse_battery(dev._command(Cmd.READ_BATTERY_STATE).data)
    snap["temperature"] = protocol.parse_temperature(dev._command(Cmd.READ_TEMPERATURE).data)
    data = bytes.fromhex(snap["ble_id"]["hex"])
    snap["ble_id_regions"] = {k: {"hex": data[a:b].hex(), "ascii": data[a:b].decode("latin-1")
                                  .replace("\x00", ".")} for k, (a, b) in REGIONS.items()}
    return snap


def diff(before: dict, after: dict) -> dict:
    a, b = bytes.fromhex(before["ble_id"]["hex"]), bytes.fromhex(after["ble_id"]["hex"])
    regions = {k: {"before": before["ble_id_regions"][k]["ascii"], "after": after["ble_id_regions"][k]["ascii"]}
               for k in REGIONS if a[slice(*REGIONS[k])] != b[slice(*REGIONS[k])]}
    if len(a) != len(b):
        regions["length"] = {"before": len(a), "after": len(b)}
    # battery and temperature drift naturally; everything else must be byte-identical
    others = [k for k in ("device_id", "read_ble", "file_list") if before[k] != after[k]]
    others += [f"file_header_{f}" for f in before["file_headers"]
               if before["file_headers"][f] != after["file_headers"][f]]
    return {"ble_id_regions_changed": regions, "other_changes": others}


def save(stamp: str, kind: str, obj: dict):
    path = LOG_DIR / f"ble_id_restore_{stamp}_{kind}.json"
    path.write_text(json.dumps(obj, indent=1), encoding="utf-8")
    print("  saved", path.relative_to(_bootstrap.ROOT))


def show(snap: dict):
    for k, v in snap["ble_id_regions"].items():
        print(f"  {k:9s} {v['ascii']!r}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--snapshot", action="store_true")
    ap.add_argument("--label", default="snapshot")
    ap.add_argument("--write", type=lambda s: int(s, 0))
    ap.add_argument("--value", choices=sorted(VALUES))
    ap.add_argument("--yes", action="store_true", help="required for --write")
    ap.add_argument("--device", default=None, help="BLE address or name")
    args = ap.parse_args()

    if args.write is not None:
        if args.write not in CANDIDATES:
            sys.exit(f"refusing opcode 0x{args.write:02X}: only {sorted(hex(c) for c in CANDIDATES)}")
        if not args.value:
            sys.exit("--write needs --value")
        if not args.yes:
            sys.exit("--write needs --yes")
    elif not args.snapshot:
        sys.exit("give --snapshot or --write")

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    with ble.ScioBLE(args.device, discover_timeout=8.0) as dev:
        print("connected:", dev.address, dev.name)
        before = snapshot(dev)
        if args.write is None:
            save(stamp, args.label, before)
            show(before)
            return
        save(stamp, "before", before)
        payload = VALUES[args.value]
        frame = protocol.build_command(args.write, payload)
        print(f"writing 0x{args.write:02X} payload {payload!r} ({len(payload)} B), frame {frame.hex()}")
        record = {"opcode": args.write, "value_name": args.value, "payload_hex": payload.hex(),
                  "payload_ascii": payload.decode("ascii"), "request_hex": frame.hex(),
                  "sent_at": datetime.now().astimezone().isoformat(timespec="seconds")}
        verdict = []
        try:
            r = dev._command(args.write, payload, allow_write=True)
            record.update(response_command=r.command, response_length=r.length, response_hex=r.data.hex())
            if r.command != args.write or r.length:
                verdict.append("unexpected reply")
        except ScioTimeout as e:
            record["error"] = f"timeout: {e}"
            verdict.append("no reply")
        save(stamp, f"write_{args.write:02x}_{args.value}", record)
        try:
            after = snapshot(dev)
        except ScioTimeout as e:
            save(stamp, "result", {"verdict": "STOP: device stopped responding", "error": str(e)})
            sys.exit("STOP: device stopped responding after the write")
        save(stamp, "after", after)
        d = diff(before, after)
        if d["other_changes"]:
            verdict.append("changes outside the BLE-ID record: " + ", ".join(d["other_changes"]))
        result = {"write": record, "diff": d,
                  "verdict": ("STOP: " + "; ".join(verdict)) if verdict else "ok"}
        save(stamp, "result", result)
        print("reply:", {k: record.get(k) for k in ("response_command", "response_length", "response_hex", "error")})
        print("changed BLE-ID regions:", json.dumps(d["ble_id_regions_changed"], indent=1) or "none")
        print("other changes:", d["other_changes"] or "none")
        print("VERDICT:", result["verdict"])
        show(after)


if __name__ == "__main__":
    main()
