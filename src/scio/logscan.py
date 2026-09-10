"""Recover scans from Android logcat dumps of the original SCiO apps.

``01_rawdata/log_files/*.txt`` are logcat captures taken while the phone app
talked to a SCiO. Each contains, interleaved:

* ``ResponseCommandParse\tbytes: 0x.. 0x..`` lines - the raw USB/BLE response
  frames, one scan being ``01BA02`` (sample) split across many lines, preceded
  by an ``01BA04`` temperature response;
* a ``DeviceInfo{...}`` line - device id, firmware, i2s tag;
* the app's own ``{"device_id": ...}`` request body, which carries the base64
  blobs *including the white reference* and both timestamps;
* sometimes the server's ``POST spectroscan2`` reply with the 331-point
  spectrum.

This is the logic of ``archive/notebooks/02_extract_log_scan.ipynb`` turned into a
library, with one deliberate change: the notebook only wrote a scan when the
**server reply** was present, so scans the app never got an answer for were
silently dropped. Here every scan whose request body is complete is returned, and
``spectrum`` is simply ``None`` when the log has no reply. That is what makes the
previously unmined logs usable.

The request body is authoritative: it is what the app actually sent, so its
base64 is used verbatim rather than re-derived from the on-the-wire hex.
"""

from __future__ import annotations

import json
import re
import struct
from pathlib import Path

from . import protocol
from .paths import portable_path
from .store import LOG_DIR, SCAN_KEYS, WHITE_KEYS, unwrap_b64

RE_BYTES = re.compile(r"ResponseCommandParse\s+bytes:((?:\s+0x[0-9A-Fa-f]{2})+)")
RE_DEVICE_INFO = re.compile(r"DeviceInfo\{(.*?)\}")
RE_REQUEST = re.compile(r'^\{"device_id".*$')
RE_SPECTRUM = re.compile(r'Response: \{"_type":"POST spectroscan2","spectrum":(.*?)\}')


def _parse_device_info(text: str) -> dict:
    """``a=1, b=true, c=x`` -> dict, with the app's own key names preserved."""
    info = {}
    for item in str(text).replace("'", "").split(", "):
        if "=" not in item:
            continue
        key, value = item.split("=", 1)
        if value.isdigit():
            info[key] = int(value)
        elif value.lower() in ("true", "false"):
            info[key] = value.lower() == "true"
        else:
            info[key] = value
    return info


def _normalize_device(info: dict) -> dict:
    """Map the app's DeviceInfo field names onto this project's device dict."""
    dev_id = info.get("deviceId") or info.get("device_id") or info.get("aptinaId")
    if dev_id:
        dev_id = str(dev_id)[-16:].upper()
    out = {
        "device_id": dev_id,
        "i2s_tag_config": info.get("i2sTagConfig") or info.get("i2s_tag_config"),
        "firmware_version": info.get("firmwareVersion") or info.get("fwVersion"),
        "dsp_id": info.get("dspId"),
        "ble_id": info.get("bleId"),
        "name": info.get("name"),
    }
    out["device_info_raw"] = info
    return {k: v for k, v in out.items() if v is not None}


def _parse_temperature(hex_str: str) -> dict | None:
    """Decode an ``01BA04`` temperature response (payload after the 5-byte header)."""
    try:
        return protocol.parse_temperature(bytes.fromhex(hex_str[10:]))
    except (ValueError, struct.error):
        return None


def parse_log(path) -> list[dict]:
    """Return one dict per scan found in *path*.

    Each dict: ``{device, temperature, wire_hex, request, spectrum, log,
    scan_index}``. ``request`` is the app's request body (base64 blobs + both
    timestamps); ``wire_hex`` is the independently reassembled response payload
    and is kept only as a cross-check - the two agree on every extracted fixture.
    """
    path = Path(path)
    scans: list[dict] = []
    device: dict = {}
    temperature = None
    wire: dict[str, str] = {}
    pending_request = None
    buf, in_blob, blob_index = "", False, 0

    def flush(spectrum):
        nonlocal pending_request, wire, temperature
        if pending_request is None:
            return
        scans.append({
            "log": portable_path(path),
            "scan_index": len(scans),
            "device": _normalize_device(device),
            "temperature": temperature,
            "wire_hex": dict(wire),
            "request": pending_request,
            "spectrum": spectrum,
        })
        pending_request, wire = None, {}

    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        m = RE_BYTES.search(line)
        if m:
            hex_str = m.group(1).replace(" 0x", "").replace("0x", "").strip()
            if "01BA04" in hex_str:
                temperature = _parse_temperature(hex_str)
            elif "01BA02" in hex_str:
                buf, in_blob, = hex_str[10:], True          # start of a blob response
            elif in_blob and not hex_str.startswith("01"):
                buf += hex_str[2:]                          # continuation: drop the seq byte
                if len(hex_str) < 40:                       # short line = last chunk
                    # Wire order is dark, sample, gradient (see README, cmd 0x02).
                    key = ("sample_dark", "sample", "sample_gradient")[blob_index % 3]
                    wire[key] = buf
                    blob_index = (blob_index + 1) % 3
                    in_blob, buf = False, ""
            continue
        m = RE_DEVICE_INFO.search(line)
        if m:
            device = _parse_device_info(m.group(1))
            continue
        if RE_REQUEST.match(line.strip()):
            flush(None)                       # a new request means the previous one got no reply
            try:
                pending_request = json.loads(line.strip())
            except ValueError:
                pending_request = None
            continue
        m = RE_SPECTRUM.search(line)
        if m and pending_request is not None:
            try:
                flush(json.loads(m.group(1)))
            except ValueError:
                flush(None)
    flush(None)
    return [s for s in scans if _is_complete(s)]


def _is_complete(scan: dict) -> bool:
    req = scan.get("request") or {}
    return all(k in req for k in ("sample", "sample_dark", "sample_white", "sample_white_dark"))


def blobs_from_request(request: dict) -> tuple[dict, dict]:
    """Split a logged request body into ``(scan_blobs, white_blobs)`` as bytes."""
    scan = {k: unwrap_b64(request[k]) for k in SCAN_KEYS if isinstance(request.get(k), str)}
    white = {k: unwrap_b64(request[k]) for k in WHITE_KEYS if isinstance(request.get(k), str)}
    return scan, white


def parse_logs(directory=LOG_DIR) -> list[dict]:
    """Parse every ``log_*.txt`` in *directory*."""
    out = []
    for p in sorted(Path(directory).glob("log_*.txt")):
        out.extend(parse_log(p))
    return out
