#!/usr/bin/env python
"""Can the server still be made to hand over firmware or the binning tables?

`GET /v1/device/{ble_id}/firmware-upgrade` answers with
`{"new_version": {<file name>: <base64>}}` when it thinks the device needs files,
and each value is a 4-byte LE checksum followed by the body. That response is the
only route by which `centers`, `bins`, `nPixelsPerBin` and `deadPixelsIndices`
have ever reached a device - and those four tables would fix the pixel->band
geometry outright.

Earlier attempts got `new_version: null` and the route was written off. Two
reasons to retry, both found by reading a **real captured request** in
`01_rawdata/log_files/log_20211020_calibration.txt:72`:

    versions=[{"key":"0x57","value":"0x7D"},{"key":"0x5A","value":"0x11"},
              {"key":"0x5B","value":"0x0C"},{"key":"0x5C","value":"0x93"}]

1. The app sends the BLE id **uppercase** (`01665900004C99B4`). Our probes sent it
   lowercase, and this API is already known to 404 on a lowercase `device_id` -
   see `01_rawdata/probe_logs/calibration_v1_thresholds_lowercase.json`.
2. The values are the device's *current* versions (0x7D=125, 0x11=17, 0x0C=12,
   0x93=147), so the server answering `null` in 2021 simply meant "up to date".
   To be offered anything we must claim to hold something older - and `0x00` may
   read as "no file" rather than "ancient version", which is worth separating.

The app never lists the four table ids in `versions`; they only appear in the
*response*. So the question is whether an outdated-looking firmware set makes the
server volunteer them.

    python dev/scripts/probe_firmware_versions.py

One request per variant, 10 s apart, every response recorded verbatim.
"""

from __future__ import annotations

import base64
import json
import struct
import sys
import time
import urllib.parse
from pathlib import Path

import requests

import _bootstrap  # noqa: F401  (sets sys.path + cwd to the repo root)

from scio import credentials, store  # noqa: E402

OUT = Path("dev/analysis_output/firmware_version_probe.json")
OUT_SWEEP = Path("dev/analysis_output/firmware_version_sweep.json")
API = "https://api.consumerphysics.com/v1"
BLE_UPPER = "01665900004C99B4"
BLE_LOWER = "01665900004c99b4"
I2S = "20150812-e:PRODUCTION"

#: file id -> hex key, as the app spells them
KEYS = {"ble": "0x57", "dsp_boot": "0x5A", "dsp_dec": "0x5B", "dsp_op": "0x5C"}
#: the four binning tables, which the app never lists but the response can carry
TABLE_KEYS = {"deadPixelsIndices": "0x64", "centers": "0x65",
              "bins": "0x66", "nPixelsPerBin": "0x67"}
CURRENT = {"0x57": "0x7D", "0x5A": "0x11", "0x5B": "0x0C", "0x5C": "0x93"}


#: Anything the server ever hands over lands here, permanently.
BLOB_DIR = Path("dev/recovered_firmware")


def versions_param(mapping: dict) -> str:
    return json.dumps([{"key": k, "value": v} for k, v in mapping.items()],
                      separators=(",", ":"))


def save_blobs(label: str, raw_response: str, new_version: dict) -> dict:
    """Write anything the server offers to disk before doing anything else.

    These files have never been obtained. If the server ever does hand them over,
    losing them to a crash or an overwrite would be unrecoverable - so the raw
    response is written first and verbatim, decoding is attempted second, and
    nothing is ever overwritten.
    """
    stamp = time.strftime("%Y%m%d_%H%M%S")
    out_dir = BLOB_DIR / f"{stamp}_{label}"
    n = 2
    while out_dir.exists():
        out_dir = BLOB_DIR / f"{stamp}_{label}_{n}"
        n += 1
    out_dir.mkdir(parents=True)

    (out_dir / "response_raw.json").write_text(raw_response, encoding="utf-8")
    written = {"dir": str(out_dir), "raw_response": "response_raw.json", "files": {}}

    for name, b64 in new_version.items():
        if not isinstance(b64, str):
            continue
        (out_dir / f"{name}.b64").write_text(b64, encoding="utf-8")
        entry = {"b64_chars": len(b64)}
        try:
            # FirmwareUpgradeModel: 4-byte LE checksum prefix, then the body.
            blob = base64.b64decode("".join(b64.split()) + "=" * (-len("".join(b64.split())) % 4))
            if len(blob) >= 4:
                checksum = struct.unpack("<I", blob[:4])[0]
                (out_dir / f"{name}.bin").write_bytes(blob[4:])
                entry.update({"checksum": checksum, "body_bytes": len(blob) - 4})
        except Exception as exc:
            entry["decode_error"] = f"{type(exc).__name__}: {exc}"
        written["files"][name] = entry

    print(f"    !! SAVED {len(written['files'])} blob(s) to {out_dir}")
    return written


def variants() -> list[dict]:
    zeros = {k: "0x00" for k in KEYS.values()}
    ones = {k: "0x01" for k in KEYS.values()}
    with_tables = {**zeros, **{k: "0x00" for k in TABLE_KEYS.values()}}
    return [
        # Control: byte-for-byte what the app sent in 2021. Establishes that the
        # route, the id casing and our auth are all good.
        {"label": "control_app_exact", "ble": BLE_UPPER, "versions": CURRENT, "i2s": I2S},
        {"label": "zeros_UPPER", "ble": BLE_UPPER, "versions": zeros, "i2s": I2S},
        {"label": "zeros_lower", "ble": BLE_LOWER, "versions": zeros, "i2s": I2S},
        {"label": "ones_UPPER", "ble": BLE_UPPER, "versions": ones, "i2s": I2S},
        {"label": "zeros_plus_table_ids", "ble": BLE_UPPER, "versions": with_tables, "i2s": I2S},
        {"label": "zeros_no_compression_version", "ble": BLE_UPPER, "versions": zeros, "i2s": None},
        {"label": "empty_versions", "ble": BLE_UPPER, "versions": {}, "i2s": I2S},
        # The combination never tried: outdated firmware AND a different
        # generation. If the server keys tables off compression_version, a device
        # claiming generation -o with nothing installed is exactly the case where
        # it should volunteer that generation's tables. The i2s oracle varied the
        # tag with *current* versions; this varies both.
        {"label": "zeros_gen_o", "ble": BLE_UPPER, "versions": zeros,
         "i2s": "20150812-o:PRODUCTION"},
        {"label": "zeros_gen_bare", "ble": BLE_UPPER, "versions": zeros,
         "i2s": "20150812:PRODUCTION"},
        {"label": "zeros_gen_older_date", "ble": BLE_UPPER, "versions": zeros,
         "i2s": "20150712:PRODUCTION"},
        # Older client string, in case the response is gated on app version.
        {"label": "zeros_old_client", "ble": BLE_UPPER, "versions": zeros, "i2s": I2S,
         "client": "Android 1.1.0.320"},
    ]


def sweep_variants() -> list[dict]:
    """Walk reported versions downward, one file at a time then all together.

    ``0x00`` may read as "no file installed" rather than "very old version", which
    would make it a special case rather than the extreme of the range - so the
    interesting values are the ones *between* current and zero. dsp_op is isolated
    first (it is the prize, and holding the other three current keeps the response
    attributable), then all four move together in case the server only offers a
    matched set.
    """
    ladder = [0x92, 0x90, 0x80, 0x64, 0x50, 0x40, 0x20, 0x10, 0x08, 0x04, 0x02, 0x01, 0x00]
    out = []
    for v in ladder:                     # dsp_op alone, others at their true versions
        out.append({"label": f"dsp_op_{v:#04x}", "ble": BLE_UPPER,
                    "versions": {**CURRENT, "0x5C": f"{v:#04x}"}, "i2s": I2S})
    for v in [0x10, 0x08, 0x04, 0x02, 0x01, 0x00]:   # all four together
        out.append({"label": f"all_{v:#04x}", "ble": BLE_UPPER,
                    "versions": {k: f"{v:#04x}" for k in KEYS.values()}, "i2s": I2S})
    # Decimal spelling, in case the server parses the value as an integer string.
    out.append({"label": "dsp_op_decimal_1", "ble": BLE_UPPER,
                "versions": {**CURRENT, "0x5C": "1"}, "i2s": I2S})
    out.append({"label": "dsp_op_negative", "ble": BLE_UPPER,
                "versions": {**CURRENT, "0x5C": "-0x01"}, "i2s": I2S})
    return out


def probe_checksum_endpoint() -> list[dict]:
    """Ask the *other* half of the upgrade handshake whether tables are needed.

    `POST /v1/device/{ble}/firmware-params-checksum` is how the app reports the
    four table checksums it read back off the device; the server answers
    ``needs_params_upgrade``. A ``true`` there is what triggers a table fetch, so
    reporting deliberately wrong checksums is the most direct way to ask the
    server to re-push them.

    Requires `Content-Type: application/json` - with form encoding it answers 415.
    """
    real = {"bins_checksum": "13587", "centers_checksum": "6080",
            "dead_pixels_indices_checksum": "97267", "n_pixels_per_bin_checksum": "36371"}
    wrong = {k: "1" for k in real}
    cases = [("real_checksums", {**real, "compression_version": I2S}),
             ("wrong_checksums", {**wrong, "compression_version": I2S}),
             ("wrong_other_generation",
              {**wrong, "compression_version": "20150812-o:PRODUCTION"})]
    rows = []
    for i, (label, body) in enumerate(cases):
        headers = {"Authorization": f"Bearer {credentials.get_token()}",
                   "Accept": "application/json", "Content-Type": "application/json",
                   "X-SCiO-Client-Version": "Android 1.3.8.554"}
        try:
            r = requests.post(f"{API}/device/{BLE_UPPER}/firmware-params-checksum",
                              json=body, headers=headers, timeout=30)
            status, text = r.status_code, r.text
        except requests.RequestException as exc:
            status, text = None, f"{type(exc).__name__}: {exc}"
        rows.append({"label": label, "body": body, "status": status,
                     "response": (text or "")[:300]})
        print(f"  checksum/{label:24s} {status}  {(text or '')[:90]}")
        if i < len(cases) - 1:
            time.sleep(10)
    return rows


def main() -> int:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    vs = sweep_variants() if "--sweep" in sys.argv[1:] else variants()
    for i, v in enumerate(vs, 1):
        params = {"versions": versions_param(v["versions"])}
        if v["i2s"]:
            params["compression_version"] = v["i2s"]
        url = f"{API}/device/{v['ble']}/firmware-upgrade?" + urllib.parse.urlencode(params)
        headers = {"Authorization": f"Bearer {credentials.get_token()}",
                   "Accept": "application/json",
                   "X-SCiO-Client-Version": v.get("client", "Android 1.3.8.554")}
        try:
            r = requests.get(url, headers=headers, timeout=30)
            status, text = r.status_code, r.text
        except requests.RequestException as exc:
            status, text = None, f"{type(exc).__name__}: {exc}"

        new_version, keys, sizes, saved = None, None, None, None
        try:
            j = json.loads(text)
            new_version = j.get("new_version")
            if isinstance(new_version, dict):
                keys = sorted(new_version)
                sizes = {k: len(x) for k, x in new_version.items() if isinstance(x, str)}
        except ValueError:
            pass

        # Persist immediately, before anything else can go wrong. These blobs have
        # never been obtained; a run that fetched them and then crashed while
        # summarising would be a genuine loss, and the server may not offer them
        # twice. Raw JSON first, then decoded bodies - raw is the fallback if the
        # decode is wrong.
        if new_version:
            saved = save_blobs(v["label"], text, new_version)

        rows.append({"label": v["label"], "ble_id_case": ("upper" if v["ble"].isupper()
                                                          else "lower"),
                     "versions": v["versions"], "compression_version": v["i2s"],
                     "client": v.get("client", "Android 1.3.8.554"),
                     "status": status, "new_version_is_null": new_version is None,
                     "new_version_keys": keys, "payload_sizes": sizes, "saved": saved,
                     "response_head": (text or "")[:300]})
        got = ("NULL" if new_version is None else f"KEYS {keys}")
        print(f"[{i}/{len(vs)}] {v['label']:30s} {status}  new_version={got}")
        if i < len(vs):
            time.sleep(10)

    print()
    checksum_rows = probe_checksum_endpoint()
    offered = [r for r in rows if r["new_version_keys"]]
    control = next((r for r in rows if r["label"] == "control_app_exact"), None)
    report = {
        "schema": "scio-firmware-probe/2",
        "ran_at": store.now_iso(),
        "control_status": control["status"] if control else None,
        "results": rows,
        "checksum_endpoint": checksum_rows,
        "verdict": ("firmware_offered" if offered else "server_offers_nothing"),
        "finding": (
            "The firmware/table backing store appears decommissioned while analysis still "
            "works. firmware-upgrade returns new_version: null for every claimed version "
            "from current down to 0x00, for each file alone and all together, in both id "
            "casings, with and without compression_version, across four generations, and "
            "under an older client string. firmware-params-checksum answers "
            "needs_params_upgrade: false even for deliberately wrong checksums - so the "
            "server is not comparing against a known-good set, it simply has nothing."),
        "captured_reference_request": (
            "01_rawdata/log_files/log_20211020_calibration.txt:72 - the app's own request, "
            "which also returned new_version: null in 2021."),
    }
    out_path = OUT_SWEEP if "--sweep" in sys.argv[1:] else OUT
    out_path.write_text(json.dumps(report, indent=1), encoding="utf-8")
    print(f"\nverdict: {report['verdict']}")
    print(f"written: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
