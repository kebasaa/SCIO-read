#!/usr/bin/env python
"""Extract the scan blobs the SCiO apps ship as mock/demo data.

The apps embed a handful of *real*, validly-signed captures from other devices and older
generations, used for offline demos:

* ``FakeJson.java`` (consumer app) - four complete request bodies (cheese, dark chocolate,
  pills, white chocolate), each with device_id, both timestamps, all six blobs and an i2s tag.
  Devices ``E027C2A6CF9435D6`` (tag ``20150812:PRODUCTION``) and ``1026A4DD1BB7158B`` (tag
  ``20150712:PRODUCTION``).
* ``resources/assets/mock/`` (consumer 1.3.8 / Lab) - a six-file scan+WR set, device
  ``503E5732B5EF1F35``, tag ``20150812-o:PRODUCTION``, with the older 1408-byte gradient body.

These are the only other-device ciphertexts available, and they are intact and signed, so they
can be submitted to the server unmodified (that is not a tamper test - see
``dev/scripts/ciphertext_oracle.py foreign``). This script only *extracts* them, into
``dev/analysis_output/foreign_scans/`` - never into ``01_rawdata/`` - with a synthetic MAC in
place of the real one the app carried, and provenance recorded as a tree-relative path only.

    SCIO_DECOMPILED_ROOT=... python dev/scripts/extract_mock_scans.py

The decompiled apps live outside this repo; set ``SCIO_DECOMPILED_ROOT`` or edit
``DECOMPILED_ROOT`` below. If the trees are absent the script says so and exits cleanly.
"""

from __future__ import annotations

import base64
import json
import os
import re
import struct
from pathlib import Path

import _bootstrap  # noqa: F401  (sets sys.path + cwd to the repo root)

from scio import store  # noqa: E402

OUT_DIR = Path("dev/analysis_output/foreign_scans")
# The decompiled apps live outside the repo. Take the path from the environment; fall back to
# a conventional location computed at runtime, so no absolute home path is baked into the file.
DECOMPILED_ROOT = Path(os.environ.get(
    "SCIO_DECOMPILED_ROOT", Path.home() / "Documents" / "__scio"))

CONSUMER = "SCiOPocketMolecularSensor_1.3.8.554_Apkpure_source_from_JADX"
FAKEJSON = f"{CONSUMER}/sources/com/consumerphysics/consumer/serverapi/FakeJson.java"
MOCK_ASSETS = f"{CONSUMER}/resources/assets/mock"

SCAN_KEYS = ("sample", "sample_dark", "sample_gradient",
             "sample_white", "sample_white_dark", "sample_white_gradient")
SYNTH_MAC = "02:00:00:00:00:00"

# The literal in FakeJson.java is one Java string; capture it without choking on escaped quotes.
_CONST = re.compile(r'String\s+(FAKE_\w*SCAN)\s*=\s*"((?:[^"\\]|\\.)*)"\s*;')


def _blob_summary(b64: str) -> dict:
    raw = base64.b64decode("".join(b64.split()))
    hdr = struct.unpack_from("<II", raw, 0) if len(raw) >= 8 else (None, None)
    return {"body_len": len(raw) - 8, "type_word": hdr[0], "second_word": hdr[1]}


def from_fakejson(root: Path) -> list[dict]:
    path = root / FAKEJSON
    if not path.exists():
        return []
    src = path.read_text(encoding="utf-8", errors="replace")
    out = []
    for m in _CONST.finditer(src):
        name = m.group(1)
        try:
            d = json.loads(m.group(2).encode().decode("unicode_escape"))
        except (ValueError, UnicodeDecodeError):
            continue
        if not all(k in d for k in ("sample", "sample_dark", "device_id", "i2s_tag_config")):
            continue
        out.append(_record(name.lower(), d.get("device_id"), d.get("i2s_tag_config"),
                           d.get("sampled_at"), d.get("sampled_white_at"),
                           {k: d[k] for k in SCAN_KEYS if k in d},
                           f"{CONSUMER}/.../FakeJson.java::{name}"))
    return out


def from_assets(root: Path) -> list[dict]:
    d = root / MOCK_ASSETS
    if not d.exists():
        return []
    name_map = {"scan-sample": "sample", "scan-dark": "sample_dark",
                "scan-gradient": "sample_gradient", "wr-sample": "sample_white",
                "wr-dark": "sample_white_dark", "wr-gradient": "sample_white_gradient"}
    blobs = {}
    for fname, key in name_map.items():
        f = d / fname
        if f.exists():
            blobs[key] = f.read_text(encoding="utf-8", errors="replace").strip()
    if "sample" not in blobs:
        return []
    # device_id / tag / timestamps are not in the asset files; the agent survey read them from
    # the app as 503E5732B5EF1F35 / 20150812-o:PRODUCTION. Record what is certain, leave the
    # rest null and let the submitter decide.
    return [_record("asset_mock_o_generation", "503E5732B5EF1F35", "20150812-o:PRODUCTION",
                    None, None, blobs, f"{CONSUMER}/resources/assets/mock/")]


def _record(name, device_id, i2s, sampled_at, sampled_white_at, blobs, provenance) -> dict:
    return {
        "schema": "scio-foreign-scan/1",
        "name": name,
        "device_id": device_id,
        "i2s_tag_config": i2s,
        "sampled_at": sampled_at,
        "sampled_white_at": sampled_white_at,
        "mobile_mac_address": SYNTH_MAC,          # never the app's real MAC
        "blobs_b64": {k: store.wrap_b64(base64.b64decode("".join(v.split())))
                      for k, v in blobs.items()},
        "blob_summary": {k: _blob_summary(v) for k, v in blobs.items()},
        "provenance": provenance,
    }


def main() -> int:
    if not DECOMPILED_ROOT.exists():
        print(f"decompiled apps not found at {DECOMPILED_ROOT}")
        print("set SCIO_DECOMPILED_ROOT to the folder holding the *_source_from_JADX trees.")
        return 1
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    records = from_fakejson(DECOMPILED_ROOT) + from_assets(DECOMPILED_ROOT)
    if not records:
        print("no mock scans extracted (trees present but constants not found)")
        return 1
    for rec in records:
        (OUT_DIR / f"{rec['name']}.json").write_text(json.dumps(rec, indent=1), encoding="utf-8")
        gens = {k: s["body_len"] for k, s in rec["blob_summary"].items()}
        print(f"  {rec['name']:26s} dev={rec['device_id']} tag={rec['i2s_tag_config']}")
        print(f"      bodies={gens}")
    print(f"\n{len(records)} foreign scan(s) -> {OUT_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
