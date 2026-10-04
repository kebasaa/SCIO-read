"""Static trace of the external-SDK scan endpoints in every supplied DEX (offline).

Records which DEX files contain the `intermediate_scan` / `aggregated-result`
route strings or their `Config` fields, and every candidate bytecode reference to
them. A positive control (`/v2/consumer/spectro-scan`, which the consumer apps do
call) must be found, or the run aborts. No app is executed and no request is sent.

    python dev/scripts/audit_sdk_endpoints.py --apps <local-app-material> --output dev/analysis_output/<new-run>/sdk_endpoints.json
"""
import argparse
from pathlib import Path

import _bootstrap  # noqa: F401
from audit_dex_boundary import dex_members
from scio_offline import dex_refs
from scio_offline import research as r

TARGETS = ("intermediate_scan", "aggregated-result", "/external_sdk/")
FIELDS = {"API_V1_UPLOAD_SCAN", "API_V1_BATCH_ANALYSIS"}
CONTROL = "/v2/consumer/spectro-scan"


ARM32_SHA256 = "9d46ae6000a652971848fecb894402727183ca07c986762198283564d9aecd9c"
ARM32_WORDS = ("intermediate", "batch")


def arm32_observations():
    """Pool-string load sites in the hash-pinned 1.5.19 ARM32 libapp, if extracted.

    Records where batch/intermediate strings are loaded and which other strings
    are loaded within 0x200 bytes. Proximity is context, not a call graph.
    """
    import json
    import struct
    from trace_arm32_diagnostics import direct_calls, pool_load, segments
    base = r.DEV / "private/flutter_1_5_19_arm32"
    lib = base / "libapp.so"
    if not lib.exists():
        return {"available": False}
    raw = lib.read_bytes()
    if r.sha(raw) != ARM32_SHA256:
        raise ValueError("unexpected 1.5.19 ARM32 libapp")
    pool = json.loads((base / "pool_strings.json").read_text(encoding="utf-8"))
    sites = []
    for off, va, n in segments(raw):
        for q in range(off, off + n - 4, 4):
            a, b = struct.unpack_from("<II", raw, q)
            key = pool_load(a, b)
            if b & 0x0FFF0000 == 0x05950000:
                key = b & 4095
            if str(key) in pool:
                sites.append((va + q - off + 4, pool[str(key)]))
    rows = [{"address": hex(addr), "string": s,
             "nearby_strings": sorted({t for a2, t in sites if abs(a2 - addr) < 0x200 and t != s
                                       and len(t) < 60 and t.isascii()})}
            for addr, s in sites if any(w in s.lower() for w in ARM32_WORDS) and len(s) < 80]
    route = next(int(x["address"], 16) for x in rows if x["string"] == "/v1/consumer/intermediate_scans/batch/")
    calls = [(c, t) for off, va, n in segments(raw) for c, t in direct_calls(raw[off:off + n - n % 4], va)]
    def routes_before(c):
        return [s for a2, s in sites if c - 0x100 <= a2 <= c and s.startswith("/")][-2:]
    # The API helper is the call after the route load that is also used for /v1/user/me.
    candidates = {t for c, t in calls if route < c < route + 0x60}
    helper = next(t for c, t in calls if t in candidates and "/v1/user/me" in routes_before(c))
    shared = [{"call": hex(c), "routes": routes_before(c)} for c, t in calls if t == helper]
    return {"available": True, "sha256": ARM32_SHA256, "string_sites": rows,
            "route_helper": hex(helper), "helper_call_sites": shared}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--apps", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    if a.output.exists():
        raise FileExistsError(a.output)
    seen, files = set(), []
    control_hits = 0
    for path in sorted((a.apps / "apk").iterdir()):
        if path.suffix.lower() not in (".apk", ".xapk"):
            continue
        for origin, raw in dex_members(path.read_bytes(), path.name):
            digest = r.sha(raw)
            if digest in seen:
                continue
            seen.add(digest)
            found = dex_refs.find_references(raw, TARGETS + (CONTROL,), FIELDS)
            control = [x for x in found["references"] if x["target"] == CONTROL]
            control_hits += len(control)
            files.append({
                "source": origin, "sha256": digest,
                "target_strings": [s for s in found["strings"] if s != CONTROL],
                "target_fields": found["fields"],
                "references": [x for x in found["references"] if x["target"] != CONTROL],
                "control_references": len(control),
            })
    if not control_hits:
        raise SystemExit("positive control not found; scanner coverage is broken")
    report = {
        "schema": "scio-sdk-endpoints/1",
        "targets": list(TARGETS), "fields": sorted(FIELDS), "positive_control": CONTROL,
        "dex_files": files,
        "arm32_1_5_19": arm32_observations(),
        "summary": {
            "dex_files": len(files),
            "files_with_target_strings": sum(bool(f["target_strings"]) for f in files),
            "candidate_references": sum(len(f["references"]) for f in files),
            "control_references": control_hits,
        },
        "interpretation": [
            "No DEX method references the external_sdk intermediate_scan route; it is a Config "
            "constant only. The consumer aggregateResult call posts device_id and batch_id.",
            "In 1.5.19, /v1/consumer/intermediate_scans/batch/ is built in one function and passed "
            "to the generic API helper shared with routes such as /v1/user/me and /v3/consumer/feed.",
            "show_intermediate_results is loaded beside Applet fields, and batch_id beside "
            "/analysis-records, /analyze-batch and /aggregated-result. The SDK constant is named "
            "API_V1_UPLOAD_SCAN beside API_V1_BATCH_ANALYSIS. Together this indicates that "
            "'intermediate' means per-scan results inside a multi-scan batch, not decoded data. "
            "Inference from names and co-location, not a traced response model.",
        ],
        "limits": dex_refs.__doc__.strip().splitlines()[-4:],
    }
    r.write_new(a.output, report)
    print(report["summary"])
    for f in files:
        for x in f["references"]:
            print(f["source"], x["class"], x["method"], x["opcode"], x["target"])


if __name__ == "__main__":
    main()
