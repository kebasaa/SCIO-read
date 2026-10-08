"""Does the fw-138 unit show the owner's sample/white separability? (bounded server probe)

We hold the contributor's valid white + skin blobs, so a same-identity role-swap (his white
blobs in the sample slots, his sample blobs in the white slots, his bare tag) is submittable -
all blobs are his, so the integrity check passes (as the owner's A0 white-swap did). The owner's
A0 established R(A,B)*R(B,A) = C(λ)^2 with a stable non-unity C. This checks whether the fw-138
unit shows the same structure, i.e. whether that calibration factor is device/generation shared.
Spectrum-domain, not a body decode. Four requests, 20 s apart, with owner controls.

    python dev/scripts/probe_fw138_separability.py --output dev/analysis_output/<new-run> [--live]
"""
import argparse
import base64
import json
from pathlib import Path

import numpy as np

import _bootstrap  # noqa: F401
from scio import cloud, store
from scio_offline import research as r
from oracle_v2 import run_jobs

OWN = "analysis_output/recovery_20261003/oracle_network/00"
CONTRIB = r.DEV / "analysis_output" / "foreign_fw138_20261008" / "scans.json"
OWNER_C_RANGE = [1.0223501318382036, 1.054725644460159]   # from the symmetry experiment


def _payload(scan_blobs, white_blobs, device_id, tag):
    now = store.now_iso()      # timestamps are inert to the server; just must be valid ISO
    return cloud.build_scan_payload({"blobs": scan_blobs, "meta": {"sampled_at": now}},
                                    {"blobs": white_blobs, "meta": {"sampled_white_at": now}},
                                    device_id, tag)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--live", action="store_true")
    a = p.parse_args()
    out = a.output.resolve()
    if not out.is_relative_to(r.DEV) or out.exists():
        raise ValueError("new output directory under dev required")

    req = json.loads((r.DEV / (OWN + "_request.json")).read_text())
    resp = json.loads((r.DEV / (OWN + "_response.json")).read_text())
    if req["name"] != "control_initial" or resp["status"] != 200:
        raise ValueError("unexpected owner control")
    scans = json.loads(CONTRIB.read_text())
    dev, tag = scans["device_id"], scans["i2s_tag_config"]
    skin = next(s for s in scans["samples"] if s["material"] == "skin")

    def B(src, key):
        return base64.b64decode(src["blobs_b64"][key])
    wr, sk = scans["white_reference"], skin
    normal = _payload(
        {"sample": B(sk, "sample"), "sample_dark": B(sk, "sample_dark"), "sample_gradient": B(sk, "sample_gradient")},
        {"sample_white": B(wr, "sample_white"), "sample_white_dark": B(wr, "sample_white_dark"),
         "sample_white_gradient": B(wr, "sample_white_gradient")}, dev, tag)
    swap = _payload(   # his white blobs into the sample slots, his sample blobs into the white slots
        {"sample": B(wr, "sample_white"), "sample_dark": B(wr, "sample_white_dark"), "sample_gradient": B(wr, "sample_white_gradient")},
        {"sample_white": B(sk, "sample"), "sample_white_dark": B(sk, "sample_dark"),
         "sample_white_gradient": B(sk, "sample_gradient")}, dev, tag)

    jobs = [
        {"name": "control_initial", "payload": req["payload"], "changes": {}, "expected_spectrum": resp["spectrum"]},
        {"name": "fw138_normal", "payload": normal, "changes": {}, "control_group": "fw138"},
        {"name": "fw138_roleswap", "payload": swap, "changes": {"roles": {"op": "swap sample<->white, all his blobs"}}, "control_group": "fw138"},
        {"name": "control_final", "payload": req["payload"], "changes": {}, "expected_spectrum": resp["spectrum"]},
    ]
    r.write_new(out / "predictions.json", {
        "hypothesis": "fw138_roleswap returns 200 + 331 finite bands (all his blobs pass the check). "
                      "If sample/white separability holds, C_fw138 = sqrt(R_normal * R_roleswap) is a "
                      "stable non-unity factor; compare its range to the owner's C (1.022-1.055).",
        "owner_C_range": OWNER_C_RANGE, "planned_requests": len(jobs)})
    run_jobs(out, jobs, a.live)
    if not a.live or (out / "halt.json").exists():
        return
    byname = {json.loads(x.read_text())["name"]: json.loads(x.read_text()) for x in out.glob("*_response.json")}
    nrm, swp = byname.get("fw138_normal"), byname.get("fw138_roleswap")
    summary = {"normal_status": nrm and nrm["status"], "roleswap_status": swp and swp["status"]}
    if nrm and swp and nrm.get("spectrum") and swp.get("spectrum"):
        Rn, Rs = np.asarray(nrm["spectrum"]), np.asarray(swp["spectrum"])
        if np.all(Rn > 0) and np.all(Rs > 0):
            C = np.sqrt(Rn * Rs)
            summary.update(C_fw138_range=[float(C.min()), float(C.max())],
                           separability_like=bool(C.min() > 0.9 and C.max() < 1.2),
                           within_owner_C_range=bool(C.min() >= OWNER_C_RANGE[0] - 0.05
                                                      and C.max() <= OWNER_C_RANGE[1] + 0.05))
    r.write_new(out / "separability_summary.json", summary)
    print(json.dumps(summary))


if __name__ == "__main__":
    main()
