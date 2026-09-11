#!/usr/bin/env python
"""Send every unprocessed canonical scan to the server and store its spectrum.

Reads ``01_rawdata/scans/*.json`` (``scio-scan/2``), writes
``02_processed_data/<scan>_spectrum.json`` (JSON only). Resumable:
records that already have a processed counterpart are skipped, so an interrupted
run can simply be re-run.

    python tools/process_all_scans.py                 # all pending, 10 s apart
    python tools/process_all_scans.py --pause 20
    python tools/process_all_scans.py --limit 5
    python tools/process_all_scans.py --report        # summarise what is on disk

A fresh access token is fetched per scan - they expire in ~14 s. A failure on one
scan is recorded and the run continues; re-running picks up whatever is left.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import _bootstrap  # noqa: F401  (sets sys.path + cwd to the repo root)

from scio import session, store  # noqa: E402
from scio.paths import portable_path  # noqa: E402

LOG = Path("02_processed_data/process_all_log.json")


def _arg(name, default=None):
    a = sys.argv[1:]
    for i, x in enumerate(a):
        if x == name and i + 1 < len(a):
            return a[i + 1]
        if x.startswith(name + "="):
            return x.split("=", 1)[1]
    return default


def report() -> int:
    s = session.summary()
    print("\nscan store")
    for k, v in s.items():
        print(f"  {k:24s} {v}")
    done = sorted(Path(store.PROCESSED_DIR).glob("*_spectrum.json"))
    n_ref, worst = 0, 0.0
    for p in done:
        d = json.loads(p.read_text(encoding="utf-8"))
        ref = (d.get("scan", {}).get("reference_spectrum") or {}).get("reflectance")
        got = d.get("spectrum", {}).get("reflectance")
        if ref and got and len(ref) == len(got):
            n_ref += 1
            worst = max(worst, max(abs(a - b) for a, b in zip(ref, got)))
    if n_ref:
        # These carry the spectrum the server returned in 2020/2021, so they are a
        # real end-to-end regression: today's answer must reproduce history.
        print(f"\n  {n_ref} processed records also hold their 2020/21 spectrum")
        print(f"  worst disagreement across all of them: max|diff| = {worst:.3e}")
    return 0


def main() -> int:
    if "--report" in sys.argv[1:]:
        return report()

    pause = float(_arg("--pause", 10.0))
    limit = int(_arg("--limit", 0) or 0) or None

    todo = session.pending()
    print(f"{len(todo)} scan(s) pending; pause {pause:.0f}s "
          f"(~{len(todo) * (pause + 1.5) / 60:.0f} min)" if not limit else
          f"{min(len(todo), limit)} of {len(todo)} pending scan(s); pause {pause:.0f}s")
    if not todo:
        return report()

    done = failed = 0
    rows = []

    def on_result(row):
        nonlocal done, failed
        rows.append(row)
        name = Path(row["scan"]).name
        if row["error"] is None:
            done += 1
            print(f"[{done + failed:3d}/{min(len(todo), limit or len(todo))}] OK   {name}")
        else:
            failed += 1
            print(f"[{done + failed:3d}/{min(len(todo), limit or len(todo))}] FAIL {name}"
                  f"  {row['error'][:90]}")

    session.process_pending(limit=limit, pause=pause, on_result=on_result)

    LOG.parent.mkdir(parents=True, exist_ok=True)
    LOG.write_text(json.dumps({
        "schema": "scio-process-log/1",
        "ran_at": store.now_iso(),
        "pause_s": pause,
        "attempted": len(rows), "succeeded": done, "failed": failed,
        "results": rows,
    }, indent=1), encoding="utf-8")

    print(f"\n{done} succeeded, {failed} failed. Log: {portable_path(LOG)}")
    if failed:
        print("Re-run to retry the failures - processed scans are skipped.")
    report()
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
