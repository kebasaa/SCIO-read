#!/usr/bin/env python
"""Does any endpoint return something *between* the blobs and the final spectrum?

Every SCiO app build declares

    Config.API_V1_UPLOAD_SCAN = "/external_sdk/intermediate_scan/widget/%s"

and **never calls it** - the constant has no call site, no request builder and no
response parser in any of the eight decompiled trees. The name is the interesting
part: an *intermediate* scan result would sit between the opaque blob and the
331-band spectrum. If the server will hand that over, it is the pixel-level data
the offline effort has been trying to reconstruct, obtained without breaking
anything.

This is a long shot with a cheap ticket. The realistic outcome is 404 or 401, in
which case it gets recorded as a closed avenue exactly as the i2s-tag oracle was,
so nobody spends an afternoon on it again.

    python dev/scripts/probe_intermediate_endpoint.py

Bounded and polite: one request per endpoint, 10 s apart, status and body recorded
verbatim. Sends one real scan the account already owns - nothing is created,
modified or deleted server-side beyond what a normal analysis request does.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import requests

import _bootstrap  # noqa: F401  (sets sys.path + cwd to the repo root)

from scio import cloud, credentials, session, store  # noqa: E402
from scio.paths import portable_path  # noqa: E402

OUT = Path("dev/analysis_output/intermediate_endpoint_probe.json")
PAUSE = 10.0
BASE = "https://api.consumerphysics.com"


def endpoints(device_id: str) -> list[dict]:
    """Every plausible spelling of the intermediate/aggregate surface.

    The widget id is unknown - the app fills `%s` from a workshop applet we do not
    have - so a placeholder is used. A 404 on a bad id and a 404 on a dead route
    look the same, which is a real limit of this probe and is recorded as such.
    """
    widget = "0"
    return [
        {"label": "intermediate_scan_v1", "method": "POST",
         "url": f"{BASE}/v1/external_sdk/intermediate_scan/widget/{widget}", "body": "scan"},
        {"label": "intermediate_scan_nover", "method": "POST",
         "url": f"{BASE}/external_sdk/intermediate_scan/widget/{widget}", "body": "scan"},
        {"label": "models_apply", "method": "POST",
         "url": f"{BASE}/v1/sdk/models/apply", "body": "scan"},
        {"label": "aggregated_result", "method": "GET",
         "url": f"{BASE}/v1/external_sdk/widget/{widget}/aggregated-result", "body": None},
        # Control: a route we know works, proving auth and payload are good. Without
        # it a wall of 404s could equally mean "our token is wrong".
        {"label": "CONTROL_spectro_scan", "method": "POST",
         "url": cloud.SPECTRO_URL, "body": "scan"},
    ]


def main() -> int:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    rec = session.load_record(sorted(Path(store.SCANS_DIR).glob("*.json"))[0])
    payload = session.to_payload(rec)
    device_id = rec["device"]["device_id"]

    results = []
    eps = endpoints(device_id)
    for i, ep in enumerate(eps, 1):
        headers = {
            "Authorization": f"Bearer {credentials.get_token()}",
            "Accept": "application/json",
            "Content-Type": "application/json",
            "X-SCiO-Client-Version": "Android 1.3.8.554",
        }
        try:
            if ep["method"] == "POST":
                r = requests.post(ep["url"], json=payload if ep["body"] else {},
                                  headers=headers, timeout=30)
            else:
                r = requests.get(ep["url"], headers=headers, timeout=30)
            status, text = r.status_code, r.text
        except requests.RequestException as exc:
            status, text = None, f"{type(exc).__name__}: {exc}"

        body_keys = None
        if text:
            try:
                parsed = json.loads(text)
                if isinstance(parsed, dict):
                    body_keys = sorted(parsed)
            except ValueError:
                pass

        row = {"label": ep["label"], "method": ep["method"],
               "url": ep["url"].replace(BASE, "<API>"),
               "status": status, "response_keys": body_keys,
               "response_head": (text or "")[:400]}
        results.append(row)
        print(f"[{i}/{len(eps)}] {ep['label']:26s} {ep['method']:4s} -> "
              f"{status}  keys={body_keys}")
        if i < len(eps):
            time.sleep(PAUSE)

    control = next((r for r in results if r["label"].startswith("CONTROL")), None)
    interesting = [r for r in results
                   if not r["label"].startswith("CONTROL") and r["status"] == 200]
    report = {
        "schema": "scio-endpoint-probe/1",
        "ran_at": store.now_iso(),
        "source_record": portable_path(rec.get("scan_uid") and
                                       sorted(Path(store.SCANS_DIR).glob("*.json"))[0]),
        "results": results,
        "control_ok": bool(control and control["status"] == 200),
        "verdict": ("intermediate_representation_available" if interesting
                    else "no_intermediate_endpoint_reachable"),
        "limits": (
            "The widget id is unknown (the app fills it from a workshop applet we do not "
            "have), so a 404 cannot distinguish 'route is dead' from 'route exists, wrong "
            "id'. The control request shows whether auth and payload were valid."),
    }
    OUT.write_text(json.dumps(report, indent=1), encoding="utf-8")
    print(f"\ncontrol (known-good endpoint) returned 200: {report['control_ok']}")
    print(f"verdict: {report['verdict']}")
    print(f"written: {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
