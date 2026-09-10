"""Fetch SCiO firmware/table blobs from the Consumer Physics server.

This replays exactly what the phone app did: log in with the user's own SCiO
account to get an OAuth bearer token, then call the per-device firmware-upgrade
endpoint. If the versions we report are older than what the server has, it
returns a ``new_version`` object with base64 blobs for each file
(``dsp_op``, ``dsp_boot``, ``dsp_dec`` and the tables) - the same blobs the app
would have cached in SharedPreferences and flashed to the device.

Credentials are never stored and never pass through anything but the request to
``auth.consumerphysics.com``. The caller supplies them (e.g. via ``getpass``);
this module keeps only the returned token.

Endpoints and field names verified from the decompiled app
(``ServerAPI.postLogin``, ``CommonServerAPI``, ``Config``, ``ModelParser``).
"""

from __future__ import annotations

import base64
import json
import re
import struct
import urllib.parse
from pathlib import Path

import requests


_TOKEN_RE = re.compile(r"access_token=([^&#\s]+)")

AUTH_BASE = "https://auth.consumerphysics.com/oauth"
API_BASE = "https://api.consumerphysics.com/v1"
SPECTRO_URL = "https://api.consumerphysics.com/v2/consumer/spectro-scan"
APP_ID = "zrjuO2M5UAetfQICtL9UAZMUqKBpcm4amDP8RU8q"
SCOPES = "workshop+widget+user_profile+change_pass+user_device+mobile_info+user_edit_profile"
REDIRECT = "https://internal.consumerphysics.com/android/auth"

# The four DSP firmware files carry a version reported to the server as a hex
# byte under these version keys (seen in the 2021 capture); the tables use their
# numeric file ids. Reporting low versions makes the server offer an upgrade.
FW_VERSION_KEYS = {
    "ble": "0x57",       # 87
    "dsp_boot": "0x5A",  # 90
    "dsp_dec": "0x5B",   # 91
    "dsp_op": "0x5C",    # 92
}


class CloudError(Exception):
    pass


def login(username: str, password: str, timeout: float = 30.0, debug: bool = False) -> str:
    """Return an OAuth bearer token for a SCiO account (implicit flow).

    POST /oauth/login authenticates and 302-redirects into /oauth/authorize,
    which 302-redirects to the app redirect_uri carrying ``access_token`` in the
    query or fragment. We follow that chain (keeping the session cookie) and
    extract the token from whichever redirect carries it.
    """
    params = {
        "response_type": "token",
        "client_id": APP_ID,
        "redirect_uri": REDIRECT,
        "scope": SCOPES,
    }
    url = f"{AUTH_BASE}/login?" + urllib.parse.urlencode(params, safe="+")
    sess = requests.Session()
    r = sess.post(url, json={"username": username, "password": password},
                  allow_redirects=False, timeout=timeout)

    for hop in range(8):
        if debug:
            print(f"  [hop {hop}] {r.status_code} {r.url}")
            if r.is_redirect:
                print(f"           -> {r.headers.get('Location','')[:160]}")
        if r.status_code in (301, 302, 303, 307, 308):
            loc = r.headers.get("Location", "")
            m = _TOKEN_RE.search(loc)
            if m:
                return urllib.parse.unquote(m.group(1))
            if not loc:
                raise CloudError("redirect without Location")
            # Do not chase the app's own redirect target (may not resolve) if it
            # carried no token; that means auth did not mint one.
            if loc.startswith(REDIRECT):
                raise CloudError(f"landed on redirect_uri without a token: {loc[:200]}")
            nxt = urllib.parse.urljoin(r.url, loc)
            r = sess.get(nxt, allow_redirects=False, timeout=timeout)
            continue
        if r.status_code == 200:
            # Token may be in the final URL, a JSON body, or an HTML page.
            m = _TOKEN_RE.search(r.url) or _TOKEN_RE.search(r.text)
            if m:
                return urllib.parse.unquote(m.group(1))
            try:
                j = r.json()
                tok = j.get("access_token") or j.get("code")
                if tok:
                    return tok
                raise CloudError(f"login 200, no token; body: {json.dumps(j)[:200]}")
            except ValueError:
                raise CloudError(f"login 200 but no token found; body: {r.text[:200]}")
        raise CloudError(f"login failed HTTP {r.status_code}: {r.text[:200]}")
    raise CloudError("too many redirects without a token")


def fetch_firmware(token: str, ble_id: str, i2s_tag: str,
                   versions: dict | None = None, timeout: float = 30.0) -> dict:
    """GET the per-device firmware-upgrade blob set.

    ``versions`` maps a version key (e.g. ``"0x5C"``) to a reported hex value
    (e.g. ``"0x01"``). Defaults to all-``0x00`` so the server treats every file
    as outdated and offers the full set. Returns the parsed ``new_version`` dict
    ``{file_name: base64_blob}`` (may be empty / None if the server offers nothing).
    """
    if versions is None:
        versions = {v: "0x00" for v in FW_VERSION_KEYS.values()}
    version_list = [{"key": k, "value": v} for k, v in versions.items()]
    params = {"versions": json.dumps(version_list, separators=(",", ":"))}
    if i2s_tag is not None:
        params["compression_version"] = i2s_tag
    url = f"{API_BASE}/device/{ble_id}/firmware-upgrade?" + urllib.parse.urlencode(params)
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "X-SCiO-Client-Version": "Android 1.3.8.554",
    }
    r = requests.get(url, headers=headers, timeout=timeout)
    if r.status_code != 200:
        raise CloudError(f"firmware-upgrade HTTP {r.status_code}: {r.text[:300]}")
    try:
        j = r.json()
    except ValueError:
        raise CloudError(f"firmware-upgrade non-JSON: {r.text[:300]}")
    return j.get("new_version") or {}


def fetch_calibration_thresholds(token: str, device_id: str, timeout: float = 30.0) -> dict:
    """GET the per-device calibration thresholds the app uses to decide on a WR.

    Verified live response (2026-09, device 8032AB45611198F1)::

        {"thresholds": {"scan_diff": 1000000000, "time_diff": 1000000000, "temp_diff": 10000}}

    ``time_diff`` is in **minutes** and the app stores it as ``* 60 * 1000`` ms.
    Every field defaults to 0 when absent, and **0 disables that rule**.
    ``device_id`` is case-sensitive (uppercase Aptina id; lowercase 404s).
    """
    url = f"{API_BASE}/device/calibration_thresholds?device_id={device_id}"
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json",
               "X-SCiO-Client-Version": "Android 1.3.8.554"}
    r = requests.get(url, headers=headers, timeout=timeout)
    if r.status_code != 200:
        raise CloudError(f"calibration_thresholds HTTP {r.status_code}: {r.text[:200]}")
    try:
        raw = r.json().get("thresholds", {})
    except ValueError:
        raise CloudError(f"calibration_thresholds non-JSON: {r.text[:200]}")
    return {
        "time_ms": int(raw.get("time_diff", 0)) * 60 * 1000,
        "scans": int(raw.get("scan_diff", 0)),
        "temperature": float(raw.get("temp_diff", 0)),
        # parsed by the app but never read by isCalibrationNeeded - kept, labelled unused
        "batch_unused": int(raw.get("min_scans_for_new_batch", 0)),
        "raw": raw,
        "source": "server",
        "fetched_at": _now_iso(),
    }


def validate_white_reference(token: str, device_id: str, white: dict, i2s_tag: str,
                             api_version: str = "v1", timeout: float = 30.0) -> dict:
    """Ask the server whether a white reference looks like a genuine WR.

    Advisory only - the app stores the WR before calling this and a ``false``
    verdict never un-stores it. Verified live response::

        {"calibration": {"is_valid": true, "calibration_id": "<uuid>"},
         "_type": "POST deviceusercalibration"}
    """
    from .store import wrap_b64
    b = white["blobs"]
    body = {
        "sampled_white_at": white["meta"].get("sampled_white_at"),
        "sample_white": wrap_b64(b["sample_white"]),
        "sample_white_dark": wrap_b64(b["sample_white_dark"]),
        "i2s_tag_config": i2s_tag,
    }
    if "sample_white_gradient" in b:
        body["sample_white_gradient"] = wrap_b64(b["sample_white_gradient"])
    url = f"https://api.consumerphysics.com/{api_version}/device/{device_id}/user_calibration"
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json",
               "Content-Type": "application/json",
               "X-SCiO-Client-Version": "Android 1.3.8.554"}
    r = requests.post(url, headers=headers, json=body, timeout=timeout)
    if r.status_code != 200:
        raise CloudError(f"user_calibration HTTP {r.status_code}: {r.text[:200]}")
    try:
        resp = r.json()
    except ValueError:
        raise CloudError(f"user_calibration non-JSON: {r.text[:200]}")
    cal = resp.get("calibration", {})
    return {
        "is_valid": cal.get("is_valid"),
        "calibration_id": cal.get("calibration_id"),
        "client_reasons": cal.get("client_reasons", []),
        "api_version": api_version,
        "checked_at": _now_iso(),
        "raw": resp,
    }


def _now_iso() -> str:
    import datetime
    return datetime.datetime.now().astimezone().isoformat(timespec="milliseconds")


def build_scan_payload(scan: dict, white: dict, device_id: str, i2s_tag: str,
                       sampled_at: str | None = None,
                       sampled_white_at: str | None = None,
                       mobile_mac_address: str = "02:00:00:00:00:00") -> dict:
    """Build the /v2/consumer/spectro-scan request body from local captures.

    ``scan``/``white`` are the dicts from ``store.load_scan`` /
    ``store.load_latest_calibration`` (raw bytes under ``blobs``). Blobs are
    encoded exactly as the app did: standard base64, wrapped at 76 cols.
    """
    from .store import wrap_b64
    b, w = scan["blobs"], white["blobs"]
    payload = {
        "device_id": device_id,
        "sampled_at": sampled_at or scan.get("meta", {}).get("sampled_at"),
        "sampled_white_at": sampled_white_at or white.get("meta", {}).get("sampled_white_at"),
        "scio_edition": "scio_edition",
        "i2s_tag_config": i2s_tag,
        "mobile_mac_address": mobile_mac_address,
        "sample": wrap_b64(b["sample"]),
        "sample_dark": wrap_b64(b["sample_dark"]),
        "sample_white": wrap_b64(w["sample_white"]),
        "sample_white_dark": wrap_b64(w["sample_white_dark"]),
        "widget_scan_attributes": [],
    }
    if "sample_gradient" in b:
        payload["sample_gradient"] = wrap_b64(b["sample_gradient"])
    if "sample_white_gradient" in w:
        payload["sample_white_gradient"] = wrap_b64(w["sample_white_gradient"])
    return payload


def analyze_scan(token: str, payload: dict, timeout: float = 30.0) -> dict:
    """POST a scan payload to spectro-scan; return the parsed JSON response.

    On success the body contains ``spectrum`` (the reflectance array) and often
    a ``wavelengths`` object ``{num_WL, start, steps}``.
    """
    import time
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
        "X-Request-ID": f"{int(time.time()*1000)}-{token}",
        "X-SCiO-Client-Version": "Android 1.3.8.554",
    }
    r = requests.post(SPECTRO_URL, json=payload, headers=headers, timeout=timeout)
    if r.status_code != 200:
        raise CloudError(f"spectro-scan HTTP {r.status_code}: {r.text[:300]}")
    try:
        return r.json()
    except ValueError:
        raise CloudError(f"spectro-scan non-JSON: {r.text[:300]}")


def spectrum_from_response(resp: dict):
    """Return (wavelengths_nm, reflectance) from a spectro-scan response."""
    spec = resp.get("spectrum")
    if spec is None:
        raise CloudError(f"no 'spectrum' in response: {json.dumps(resp)[:200]}")
    reflectance = [float(x) for x in spec]
    wl = resp.get("wavelengths") or {}
    start = wl.get("start", 740)
    steps = wl.get("steps", 1)
    wavelengths = [start + i * steps for i in range(len(reflectance))]
    return wavelengths, reflectance


def save_firmware(new_version: dict, out_dir: Path | str) -> list[Path]:
    """Decode each base64 blob (stripping the 4-byte checksum prefix) to *.bin."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for name, b64 in new_version.items():
        if not isinstance(b64, str):
            continue
        raw = base64.b64decode("".join(b64.split()) + "=" * (-len("".join(b64.split())) % 4))
        if len(raw) < 4:
            continue
        # FirmwareUpgradeModel: 4-byte little-endian checksum prefix, then the body.
        checksum = struct.unpack("<I", raw[:4])[0]
        p = out_dir / f"{name}.bin"
        p.write_bytes(raw[4:])
        (out_dir / f"{name}.checksum").write_text(str(checksum))
        written.append(p)
    return written
