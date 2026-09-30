#!/usr/bin/env python
"""Is the newest app's backend (scionir.com) the same service as consumerphysics.com?

The Flutter SCiO Analyzer talks to ``api.scionir.com`` / ``auth.scionir.com`` rather than
``api.consumerphysics.com``. If that is an independent backend, its firmware store might be
alive even though the old one is decommissioned (see ``probe_firmware_versions.py``). If it
is the same backend behind a new name, nothing changes.

This is deliberately cheap and read-only:

* DNS only first - which addresses do the hosts resolve to?
* **Unauthenticated** GETs of two endpoints the newest app has and the old ones lack
  (``/v1/client_version_status``, ``/v1/rollout_config``), on both hosts.
* One authenticated GET of ``/v1/configuration`` on the *old* host only, where our token is
  already valid. **No credential is sent to any scionir.com host** - that needs an explicit
  decision, because it would put stored account credentials in front of a service the user
  has not authorised this project to use.

5 s between requests; every response recorded verbatim.
"""

from __future__ import annotations

import json
import socket
import time
from pathlib import Path

import requests

import _bootstrap  # noqa: F401  (sets sys.path + cwd to the repo root)

from scio import credentials, store  # noqa: E402

OUT = Path("dev/analysis_output/new_host_probe.json")
HOSTS = ["api.consumerphysics.com", "api.scionir.com", "auth.scionir.com",
         "lab.consumerphysics.com", "dev.scionir.com"]
PATHS = ["/v1/client_version_status", "/v1/rollout_config", "/"]


def resolve(host: str) -> list[str]:
    try:
        return sorted({ai[4][0] for ai in socket.getaddrinfo(host, 443, proto=socket.IPPROTO_TCP)})
    except OSError as exc:
        return [f"unresolved: {exc}"]


def fetch(url: str, headers=None) -> dict:
    try:
        r = requests.get(url, headers=headers or {}, timeout=20, allow_redirects=False)
        return {"url": url, "status": r.status_code,
                "server": r.headers.get("Server"), "content_type": r.headers.get("Content-Type"),
                "location": r.headers.get("Location"), "body": r.text[:300]}
    except requests.RequestException as exc:
        return {"url": url, "status": None, "error": f"{type(exc).__name__}: {exc}"[:200]}


def main() -> int:
    dns = {h: resolve(h) for h in HOSTS}
    print("DNS")
    for h, ips in dns.items():
        print(f"  {h:26s} {', '.join(ips)}")
    same = bool(set(dns["api.consumerphysics.com"]) & set(dns["api.scionir.com"]))
    print(f"\napi.consumerphysics.com and api.scionir.com share an address: {same}")

    probes = []
    for host in ("api.consumerphysics.com", "api.scionir.com"):
        for path in PATHS:
            rec = fetch(f"https://{host}{path}")
            probes.append({**rec, "auth": "none"})
            print(f"  {host:24s} {path:28s} {rec.get('status')}  {(rec.get('body') or rec.get('error') or '')[:70]!r}")
            time.sleep(5)

    # old host only, where the token is already valid
    tok = credentials.get_token()
    rec = fetch("https://api.consumerphysics.com/v1/configuration",
                {"Authorization": f"Bearer {tok}", "Accept": "application/json"})
    probes.append({**rec, "auth": "bearer (old host only)"})
    print(f"  {'api.consumerphysics.com':24s} {'/v1/configuration':28s} {rec.get('status')}  "
          f"{(rec.get('body') or rec.get('error') or '')[:70]!r}")

    OUT.write_text(json.dumps({
        "schema": "scio-new-host-probe/1", "ran_at": store.now_iso(),
        "dns": dns, "share_an_address": same, "probes": probes,
        "credentials_sent_to_scionir": False,
    }, indent=1), encoding="utf-8")
    print(f"\nwritten: {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
