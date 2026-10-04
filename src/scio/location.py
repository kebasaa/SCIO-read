"""Where a scan was taken: the triggering computer's own location, stored locally.

Every canonical record carries a ``mobile_GPS`` block shaped like the one the
phone app attached to its requests (``latitude``, ``longitude``, ``locality``,
``country``, ``admin_area``, ``address_line``), plus ``location_meta`` saying where
the fix came from. When no fix is available the fields are simply empty.

**Privacy.** The location is written to the local record only. It is *never* sent
to the vendor server unless the caller passes ``send_location=True`` to
:func:`scio.session.process` / :func:`scio.session.process_pending`. That argument
is the user's consent. No lookup here talks to the network: there is deliberately
no IP-based geolocation, which would disclose the address to a third party, and no
reverse geocoding, so the text fields stay empty unless the caller fills them in.

Providers, tried in order, each optional and each failing quietly:

* Windows: ``winsdk``/``winrt`` ``Geolocator`` if installed, else the built-in
  Windows location service via PowerShell (``System.Device.Location``). Both obey
  the Windows privacy setting *Location services*.
* Linux: GeoClue's ``where-am-i`` demo client, if present.
* macOS: ``CoreLocationCLI``, if on ``PATH``.

Geolocation is **off by default**. Enable it per call (``capture(..., geolocate=True)``)
or globally with the environment variable ``SCIO_GEOLOCATION=1``. GPS data is never
published to the public repository: ``tools/check_public_safety.py`` (run by the
pre-commit hook) refuses any file carrying real coordinates.
"""

from __future__ import annotations

import json
import os
import platform
import re
import shutil
import subprocess
from datetime import datetime

GPS_KEYS = ("latitude", "longitude", "locality", "country", "admin_area", "address_line")
ENV_SWITCH = "SCIO_GEOLOCATION"
DEFAULT_TIMEOUT = 10.0

_PS_SCRIPT = r"""
Add-Type -AssemblyName System.Device
$w = New-Object System.Device.Location.GeoCoordinateWatcher([System.Device.Location.GeoPositionAccuracy]::High)
$null = $w.TryStart($false, [TimeSpan]::FromMilliseconds(500))
$deadline = (Get-Date).AddSeconds(__TIMEOUT__)
while ($w.Status -ne 'Ready' -and $w.Permission -ne 'Denied' -and (Get-Date) -lt $deadline) { Start-Sleep -Milliseconds 200 }
$c = $w.Position.Location
$o = @{ permission = [string]$w.Permission; status = [string]$w.Status; unknown = $c.IsUnknown }
if (-not $c.IsUnknown) {
  $o.latitude = $c.Latitude; $o.longitude = $c.Longitude
  $o.accuracy_m = $c.HorizontalAccuracy
  if (-not [double]::IsNaN($c.Altitude)) { $o.altitude_m = $c.Altitude }
}
$w.Stop()
$o | ConvertTo-Json -Compress
"""


def enabled_by_default() -> bool:
    """Off unless ``SCIO_GEOLOCATION`` is set to 1/true/yes/on."""
    return os.environ.get(ENV_SWITCH, "0").strip().lower() in ("1", "true", "yes", "on")


def empty_gps() -> dict:
    return {"latitude": None, "longitude": None, "locality": "", "country": "",
            "admin_area": "", "address_line": ""}


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="milliseconds")


def _valid(lat, lon) -> bool:
    try:
        lat, lon = float(lat), float(lon)
    except (TypeError, ValueError):
        return False
    return -90 <= lat <= 90 and -180 <= lon <= 180 and not (lat == 0 and lon == 0)


def _fix(lat, lon, source, accuracy=None, altitude=None) -> dict | None:
    if not _valid(lat, lon):
        return None
    return {"latitude": float(lat), "longitude": float(lon), "source": source,
            "accuracy_m": None if accuracy is None else float(accuracy),
            "altitude_m": None if altitude is None else float(altitude)}


# ------------------------------------------------------------------ providers
def _windows_winrt(timeout: float):
    try:
        import asyncio
        try:
            from winsdk.windows.devices.geolocation import Geolocator
        except ImportError:
            from winrt.windows.devices.geolocation import Geolocator
    except ImportError:
        return None, "winsdk/winrt not installed"

    async def _get():
        pos = await Geolocator().get_geoposition_async()
        c = pos.coordinate
        point = c.point.position
        return _fix(point.latitude, point.longitude, "windows-geolocator", c.accuracy, point.altitude)

    try:
        fix = asyncio.run(asyncio.wait_for(_get(), timeout))
    except Exception as exc:          # denied, disabled, timeout, no sensor
        return None, f"windows-geolocator: {type(exc).__name__}"
    return fix, None if fix else "windows-geolocator: no fix"


def _windows_powershell(timeout: float):
    exe = shutil.which("powershell") or shutil.which("powershell.exe")
    if not exe:
        return None, "powershell not found"
    script = _PS_SCRIPT.replace("__TIMEOUT__", str(int(max(1, timeout))))
    try:
        out = subprocess.run([exe, "-NoProfile", "-NonInteractive", "-Command", script],
                             capture_output=True, text=True, timeout=timeout + 15)
        data = json.loads(out.stdout.strip() or "{}")
    except (OSError, subprocess.SubprocessError, ValueError) as exc:
        return None, f"windows-location-service: {type(exc).__name__}"
    if data.get("unknown", True):
        return None, (f"windows-location-service: no fix (permission {data.get('permission')}, "
                      f"status {data.get('status')})")
    fix = _fix(data.get("latitude"), data.get("longitude"), "windows-location-service",
               data.get("accuracy_m"), data.get("altitude_m"))
    return fix, None if fix else "windows-location-service: invalid fix"


def _linux_geoclue(timeout: float):
    exe = next((p for p in ("/usr/libexec/geoclue-2.0/demos/where-am-i",
                            "/usr/lib/geoclue-2.0/demos/where-am-i") if os.path.exists(p)), None)
    if not exe:
        return None, "geoclue where-am-i not found"
    try:
        out = subprocess.run([exe, "-t", str(int(max(1, timeout)))], capture_output=True,
                             text=True, timeout=timeout + 5).stdout
    except (OSError, subprocess.SubprocessError) as exc:
        return None, f"geoclue: {type(exc).__name__}"
    lat = re.search(r"Latitude:\s*(-?[\d.]+)", out)
    lon = re.search(r"Longitude:\s*(-?[\d.]+)", out)
    acc = re.search(r"Accuracy:\s*([\d.]+)", out)
    fix = _fix(lat and lat.group(1), lon and lon.group(1), "geoclue", acc and acc.group(1))
    return fix, None if fix else "geoclue: no fix"


def _macos_corelocationcli(timeout: float):
    exe = shutil.which("CoreLocationCLI")
    if not exe:
        return None, "CoreLocationCLI not found"
    try:
        out = subprocess.run([exe, "--format", "%latitude %longitude %h_accuracy"],
                             capture_output=True, text=True, timeout=timeout + 5).stdout.split()
    except (OSError, subprocess.SubprocessError) as exc:
        return None, f"corelocation: {type(exc).__name__}"
    fix = _fix(*(out[:2] if len(out) >= 2 else (None, None)), "corelocation",
               out[2] if len(out) >= 3 else None)
    return fix, None if fix else "corelocation: no fix"


def _providers():
    system = platform.system()
    if system == "Windows":
        return [_windows_winrt, _windows_powershell]
    if system == "Linux":
        return [_linux_geoclue]
    if system == "Darwin":
        return [_macos_corelocationcli]
    return []


def get_fix(timeout: float = DEFAULT_TIMEOUT) -> tuple[dict | None, list[str]]:
    """Ask the local location providers in turn. Never raises.

    Returns ``(fix, notes)``; ``fix`` is ``None`` when no provider produced a
    position, and ``notes`` records why each provider gave nothing.
    """
    notes = []
    for provider in _providers():
        try:
            fix, note = provider(timeout)
        except Exception as exc:      # a provider must never break a capture
            fix, note = None, f"{provider.__name__}: {type(exc).__name__}"
        if fix:
            return fix, notes
        notes.append(note)
    if not notes:
        notes.append(f"no location provider for {platform.system() or 'this platform'}")
    return None, notes


def scan_location(enabled: bool | None = None, manual: dict | None = None,
                  timeout: float = DEFAULT_TIMEOUT) -> tuple[dict, dict]:
    """``(mobile_GPS, location_meta)`` for a new record.

    *manual* (e.g. coordinates from a phone) takes precedence over the computer's
    providers; it may hold any of :data:`GPS_KEYS`. With geolocation disabled and no
    *manual* value, the fields are empty.
    """
    enabled = enabled_by_default() if enabled is None else bool(enabled)
    gps = empty_gps()
    meta = {"enabled": enabled, "source": None, "acquired_at": None, "accuracy_m": None,
            "altitude_m": None, "notes": [], "sent_to_server": False}
    if manual:
        if not _valid(manual.get("latitude"), manual.get("longitude")):
            raise ValueError("manual location needs valid latitude and longitude")
        gps.update({k: manual[k] for k in GPS_KEYS if manual.get(k) is not None})
        gps["latitude"], gps["longitude"] = float(gps["latitude"]), float(gps["longitude"])
        meta.update(source=manual.get("source", "manual"), acquired_at=_now(),
                    accuracy_m=manual.get("accuracy_m"))
        return gps, meta
    if not enabled:
        meta["notes"].append("geolocation disabled")
        return gps, meta
    fix, notes = get_fix(timeout)
    meta["notes"] = notes
    if fix:
        gps["latitude"], gps["longitude"] = fix["latitude"], fix["longitude"]
        meta.update(source=fix["source"], acquired_at=_now(),
                    accuracy_m=fix["accuracy_m"], altitude_m=fix["altitude_m"])
    return gps, meta


def has_fix(gps: dict | None) -> bool:
    return bool(gps) and _valid(gps.get("latitude"), gps.get("longitude"))
