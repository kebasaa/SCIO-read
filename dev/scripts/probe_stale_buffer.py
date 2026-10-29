"""Does a read-only reply after a scan leak reply-buffer bytes that were never sent?

An outside report (email/SCIO_GITHUB_RESEARCH_SUMMARY.md) saw, 44/44 times on a fw-151
unit, bytes 13-15 of the battery reply equal bytes 13-15 of the gradient blob sent just
before it, consistent with stale buffer contents. These are opaque bytes already
received. Byte comparisons cannot establish encryption, plaintext, or key material.

Live, owner unit over USB, read-only opcodes only (``raw_command`` refuses anything else):

  baseline   two raw replies of each probe opcode before any scan
  per round  scan -> battery;  scan -> <one other opcode, rotating>;  temperature -> battery

Every reply byte is classed as
  same_offset  equals the same offset of a blob from the scan just before
  in_blobs     inside a >=3-byte run that occurs anywhere in this session's blobs
  baseline     equals the same offset of a pre-scan reply of the same opcode
  unexplained  none of these

    python dev/scripts/probe_stale_buffer.py --output dev/analysis_output/stale_buffer_20261028 --rounds 10
    python dev/scripts/probe_stale_buffer.py --replay <rounds.json> --output <new directory under dev/>
"""
import argparse
import base64
import json
import re
import struct
import time
from collections import Counter
from pathlib import Path

import _bootstrap  # noqa: F401
from scio import protocol
from scio.protocol import Cmd
from scio_offline import research as r

#: read-only opcodes probed; payload for 0x87 is an unsupported file id
PROBES = {
    "device_status": (Cmd.READ_DEVICE_STATUS, b""),
    "device_id": (Cmd.READ_DEVICE_ID, b""),
    "temperature": (Cmd.READ_TEMPERATURE, b""),
    "battery": (Cmd.READ_BATTERY_STATE, b""),
    "ble_id": (Cmd.READ_BLE_ID, b""),
    "ble_status": (Cmd.READ_BLE_STATUS, b""),
    "ble_config": (Cmd.READ_BLE, b""),
    "file_header_unsupported": (Cmd.READ_FILE_HEADER, struct.pack("<I", 0x58)),
}
#: bytes covered by the documented parser; anything past this is padding
#: Battery bytes 8..14 are not documented by the parser. Some vary slowly;
#: that observation does not establish their meaning or exclude residue.
PARSED_LEN = {"device_status": 8, "device_id": 26, "temperature": 12, "battery": 8,
              "ble_id": 130, "ble_status": 0, "ble_config": 0, "file_header_unsupported": 16}
# Device-id parser skips bytes 8..15; a prefix length alone would hide that gap.
UNKNOWN_GAPS = {"device_id": range(8, 16)}
ROTATION = [k for k in PROBES if k != "battery"]
MAX_ROUNDS = 20
RUN = 3


# ------------------------------------------------------------------ analysis (pure)
def _ngrams(blobs, n=RUN):
    out = set()
    for b in blobs:
        out.update(b[i:i + n] for i in range(len(b) - n + 1))
    return out


def classify(reply: bytes, prev_scan: dict, session_grams: set, baseline: list) -> list:
    """Class of every byte of *reply* (see module docstring); first match wins."""
    in_run = [False] * len(reply)
    for i in range(len(reply) - RUN + 1):
        if reply[i:i + RUN] in session_grams:
            for j in range(i, i + RUN):
                in_run[j] = True
    out = []
    for i, byte in enumerate(reply):
        if any(i < len(b) and b[i] == byte and any(
                0 <= k < min(len(reply), len(b)) and b[k] == reply[k]
                for k in (i - 1, i + 1)) for b in prev_scan.values()):
            out.append("same_offset")
        elif in_run[i]:
            out.append("in_blobs")
        elif any(i < len(b) and b[i] == byte for b in baseline):
            out.append("baseline")
        else:
            out.append("unexplained")
    return out


def analyse(rows: list, baseline: dict) -> dict:
    """rows: [{probe, reply(bytes), prev_scan({role: bytes}) or None, session_blobs [bytes]}]."""
    per_probe, events = {}, []
    for row in rows:
        name = row["probe"]
        cls = classify(row["reply"], row["prev_scan"] or {}, _ngrams(row["session_blobs"]),
                       baseline.get(name, []))
        pad_from = PARSED_LEN.get(name, 0)
        stats = per_probe.setdefault(name, {"n": 0, "lengths": Counter(), "classes": Counter(),
                                            "padding_classes": Counter(), "same_offset_positions": Counter(),
                                            "unexplained_positions": Counter()})
        stats["n"] += 1
        stats["lengths"][len(row["reply"])] += 1
        for i, c in enumerate(cls):
            stats["classes"][c] += 1
            unknown = i >= pad_from or i in UNKNOWN_GAPS.get(name, ())
            if unknown:
                stats["padding_classes"][c] += 1
            if c == "same_offset":
                stats["same_offset_positions"][i] += 1
            if c == "unexplained" and unknown:
                stats["unexplained_positions"][i] += 1
        events.append({"probe": name, "context": row.get("context"), "len": len(row["reply"]),
                       "classes": "".join(c[0] for c in cls)})
    summary = {k: {"n": v["n"], "lengths": dict(v["lengths"]), "classes": dict(v["classes"]),
                   "padding_classes": dict(v["padding_classes"]),
                   "same_offset_positions": dict(sorted(v["same_offset_positions"].items())),
                   "unexplained_padding_positions": dict(sorted(v["unexplained_positions"].items()))}
               for k, v in per_probe.items()}
    unexplained = sum(v["padding_classes"].get("unexplained", 0) for v in per_probe.values())
    return {"per_probe": summary, "events": events,
            "unexplained_padding_bytes": unexplained,
            "unknown_region_starts": PARSED_LEN,
            "unknown_gaps": {k: list(v) for k, v in UNKNOWN_GAPS.items()},
            "interpretation": "Classes are byte matches, not proof of origin. Padding means bytes "
                              "outside the documented parser, not proven unused memory.",
            "verdict": ("No unmatched bytes outside documented parser coverage in these replies; "
                        "this does not establish provenance or exclude other disclosures.") if unexplained == 0 else
                       "UNEXPLAINED bytes outside documented parser coverage; meaning unresolved"}


def battery_tail(replies: list, scans: list) -> dict:
    """Which byte of the preceding scan's blobs does battery byte 15 equal? (rounds.json shapes)"""
    hits, n = Counter(), 0
    for rep in replies:
        if rep["probe"] != "battery":
            continue
        scan = scans[_scan_index(rep, len(scans))]
        b = bytes.fromhex(rep["hex"])
        n += 1
        for role, blob in scan.items():
            if len(b) > 15 and len(blob) > 15 and blob[15] == b[15]:
                hits[role] += 1
    return {"n_battery_replies": n, "byte15_equals_prev_blob_byte15": dict(hits)}


def _scan_index(rep, count):
    context = rep.get("context", "")
    match = re.fullmatch(r"r(\d+):scan->(.+)", context)
    if not match or rep.get("probe") not in PROBES:
        raise ValueError("invalid reply context or probe")
    rnd, chain = int(match[1]), match[2]
    other = ROTATION[rnd % len(ROTATION)]
    expected = {"battery": 2 * rnd, other: 2 * rnd + 1,
                f"{other}->temperature->battery": 2 * rnd + 1}
    if chain not in expected or chain.split("->")[-1] != rep["probe"]:
        raise ValueError("reply context does not match capture schedule")
    idx = expected[chain]
    if idx >= count:
        raise ValueError("reply references a missing scan")
    return idx


def replay(path: Path) -> dict:
    """Reanalyse saved evidence without device access, network, or source mutation."""
    raw = path.read_bytes()
    saved = json.loads(raw)
    scans = [{k: base64.b64decode(v, validate=True) for k, v in s.items()}
             for s in saved["scans_b64"]]
    if not scans or len(scans) % 2:
        raise ValueError("saved run must have complete scan pairs")
    baseline = {k: [bytes.fromhex(v) for v in vs] for k, vs in saved["baseline"].items()}
    rows, seen = [], set()
    for rep in saved["replies"]:
        idx = _scan_index(rep, len(scans))
        if rep["context"] in seen:
            raise ValueError("duplicate reply context")
        seen.add(rep["context"])
        rows.append({"probe": rep["probe"], "context": rep["context"],
                     "reply": bytes.fromhex(rep["hex"]), "prev_scan": scans[idx],
                     "session_blobs": [b for s in scans[:idx + 1] for b in s.values()]})
    expected = []
    for rnd in range(len(scans) // 2):
        other = ROTATION[rnd % len(ROTATION)]
        expected.extend([f"r{rnd}:scan->battery", f"r{rnd}:scan->{other}",
                         f"r{rnd}:scan->{other}->temperature->battery"])
    result = analyse(rows, baseline)
    result.update({"schema_version": 3, "source_sha256": r.sha(raw),
                   "n_scans": len(scans), "n_replies": len(rows),
                   "missing_reply_contexts": [c for c in expected if c not in seen],
                   "baseline_counts": {k: len(baseline.get(k, [])) for k in PROBES},
                   "unobserved_probes": sorted(set(PROBES) - {row["probe"] for row in rows}),
                   "capture_errors": saved.get("errors", []),
                   "battery_tail": battery_tail(saved["replies"], scans)})
    return result


# ------------------------------------------------------------------ live
def _query(dev, name):
    cmd, payload = PROBES[name]
    return dev.raw_command(cmd, payload)[0].data


def _scan(dev, fw):
    n = protocol.num_responses_for_firmware(fw)
    resp = dev.raw_command(Cmd.SAMPLE_SPECTRUM, n_responses=n)
    roles = ["dark", "sample", "gradient"][:n]
    return {role: x.data for role, x in zip(roles, resp)}


def run_live(out: Path, rounds: int):
    from scio.usb import ScioUSB, find_scio_ports
    ports = [p for p in find_scio_ports() if p["is_scio"]]
    if len(ports) != 1:
        raise RuntimeError("requires exactly one SCiO USB port (steady blue; power-cycle if silent)")
    rows, baseline, scans, log = [], {}, [], []
    with ScioUSB(ports[0]["device"], timeout=5) as dev:
        info = dev.read_device_info()
        fw = info.get("firmware_version", 0)
        for name in PROBES:
            baseline[name] = []
            for _ in range(2):
                try:
                    baseline[name].append(_query(dev, name))
                except Exception as exc:
                    log.append({"stage": "baseline", "probe": name, "error": f"{type(exc).__name__}: {exc}"})

        def record(name, prev, context):
            try:
                reply = _query(dev, name)
            except Exception as exc:
                log.append({"stage": context, "probe": name, "error": f"{type(exc).__name__}: {exc}"})
                return
            rows.append({"probe": name, "reply": reply, "prev_scan": prev, "context": context,
                         "session_blobs": [b for s in scans for b in s.values()]})

        for i in range(rounds):
            s = _scan(dev, fw); scans.append(s)
            record("battery", s, f"r{i}:scan->battery")
            s = _scan(dev, fw); scans.append(s)
            other = ROTATION[i % len(ROTATION)]
            record(other, s, f"r{i}:scan->{other}")
            _query(dev, "temperature")
            record("battery", s, f"r{i}:scan->{other}->temperature->battery")
            print(f"round {i + 1}/{rounds}", flush=True)
            time.sleep(0.2)

    b64 = lambda b: base64.b64encode(b).decode()
    r.write_new(out / "rounds.json", {
        "device": {k: info.get(k) for k in ("device_id", "firmware_version", "i2s_tag_config")},
        "baseline": {k: [v.hex() for v in vs] for k, vs in baseline.items()},
        "scans_b64": [{k: b64(v) for k, v in s.items()} for s in scans],
        "replies": [{"probe": x["probe"], "context": x["context"], "hex": x["reply"].hex()} for x in rows],
        "errors": log})
    result = analyse(rows, baseline)
    r.write_new(out / "analysis.json", result)
    return result


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--output", type=Path, required=True, help="new dir under dev/")
    p.add_argument("--rounds", type=int, default=10)
    p.add_argument("--replay", type=Path, help="offline analysis of saved rounds.json")
    a = p.parse_args()
    if not 1 <= a.rounds <= MAX_ROUNDS:
        raise ValueError(f"rounds must be 1..{MAX_ROUNDS}")
    out = a.output.resolve()
    if not out.is_relative_to(r.DEV):
        raise ValueError("output must be under dev/")
    if out.exists():
        raise FileExistsError("choose a new output directory")
    if a.replay:
        res = replay(a.replay)
        r.write_new(out / "analysis_v3.json", res)
    else:
        res = run_live(out, a.rounds)
    for k, v in res["per_probe"].items():
        print(k, v["n"], v["lengths"], v["padding_classes"], "same-offset@", v["same_offset_positions"])
    print(res["verdict"])


if __name__ == "__main__":
    main()
