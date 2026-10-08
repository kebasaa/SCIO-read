"""Read-only object-temperature check on the connected unit (READ_TEMPERATURE only).

Takes a short series of temperature reads so you can watch obj_t while the sensor is in open
air, then pressed to skin. No scans, no writes, no state change - only command 0x04. Purpose:
see whether word 2 (obj_t) is live on this fw-147 unit (it is 0 historically; live on a fw-138
unit). Point the sensor at open air for the first reads, then hold it to your skin.

    python dev/scripts/read_object_temperature.py --output dev/analysis_output/<new>/objt.json
"""
import argparse
import time
from pathlib import Path

import _bootstrap  # noqa: F401
from scio.usb import ScioUSB, find_scio_ports
from scio_offline import research as r


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--output", required=True, type=Path)
    p.add_argument("--reads", type=int, default=12)
    p.add_argument("--gap", type=float, default=1.5)
    a = p.parse_args()
    if not 1 <= a.reads <= 60:
        raise ValueError("reads must be 1..60")
    out = a.output.resolve()
    if not out.is_relative_to(r.DEV) or out.exists():
        raise ValueError("new output path under dev required")

    ports = [x for x in find_scio_ports() if x.get("is_scio")]
    if len(ports) != 1:
        raise RuntimeError(f"requires exactly one detected SCiO port (found {len(ports)}); "
                           "connect the unit and wake it to steady blue, then retry")
    rows = []
    with ScioUSB(ports[0]["device"], timeout=3) as device:
        info = device.read_device_info()
        print(f"fw {info.get('firmware_version')}  device {info.get('device_id')}")
        print("Point the sensor at OPEN AIR, then press it to SKIN as the reads continue.")
        for i in range(a.reads):
            t = device.read_temperature()
            rows.append({"i": i, "obj_t": t["obj_t"], "cmos_t": round(t["cmos_t"], 2),
                         "chip_t": t["chip_t"], "raw_u32": t["raw_u32"]})
            print(f"  read {i:2d}: obj_t={t['obj_t']:6.2f}  cmos_t={t['cmos_t']:5.2f}  "
                  f"chip_t={t['chip_t']:5.2f}", flush=True)
            if i < a.reads - 1:
                time.sleep(a.gap)
    objs = [x["obj_t"] for x in rows]
    report = {"schema": "scio-objt/1", "device_id": info.get("device_id"),
              "firmware_version": info.get("firmware_version"),
              "reads": rows, "obj_t_min": min(objs), "obj_t_max": max(objs),
              "obj_t_live": bool(max(objs) != 0.0 and (max(objs) - min(objs)) > 0.5),
              "note": "Read-only; command 0x04 only; no scans or writes. obj_t_live means it "
                      "moved with the target, like the fw-138 unit."}
    r.write_new(out, report)
    print(f"\nobj_t range {report['obj_t_min']:.2f}..{report['obj_t_max']:.2f}  "
          f"live={report['obj_t_live']}")


if __name__ == "__main__":
    main()
