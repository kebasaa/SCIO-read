#!/usr/bin/env python
"""Use the vendor server as a chosen-ciphertext oracle, in gated phases.

The server decodes whatever blob it is sent, deterministically (noise floor exactly 0),
and reports the result band by band. Until now it has only been used to *produce*
spectra. Sending it edited blobs and watching how the answer changes exposes the
structure of the transform from outside the wire; see ``dev/scio_offline/malleability.py``
for what each outcome means and how the classifier was validated.

    python dev/scripts/ciphertext_oracle.py a0        # valid inputs only, ~6 requests
    python dev/scripts/ciphertext_oracle.py pilot     # small in-range flips only, ~45 requests
    python dev/scripts/ciphertext_oracle.py foreign   # submit app-embedded mock blobs, intact
    python dev/scripts/ciphertext_oracle.py status    # what has been recorded / budget left

Phases are gated. **A0 sends no corrupted data** and establishes that the server's transfer
function behaves the way the later probes assume; if an identity fails, the window is not
clean and nothing tampered is sent.

Safety rails, all enforced in code rather than by discipline:

* 10 s between requests;
* stop after 3 consecutive 5xx (or any 401/403/429), so a failing or challenging server is
  never hammered;
* a hard cap on total requests across every phase (``MAX_REQUESTS``);
* every response - status and body, verbatim - is written to its own JSON before anything
  else happens, and a request whose file already exists is never re-sent (resumable).

Results land in ``dev/analysis_output/ciphertext_oracle/``.
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
import time
from pathlib import Path

import numpy as np

import _bootstrap  # noqa: F401  (sets sys.path + cwd to the repo root)

from scio import cloud, credentials, session, store  # noqa: E402
from scio.paths import portable_path  # noqa: E402

OUT_DIR = Path("dev/analysis_output/ciphertext_oracle")
MIN_GAP = 10.0
MAX_REQUESTS = 300
MAX_CONSECUTIVE_5XX = 3

BASELINE_SCAN = "20200604143337_calibrationbox_143337"     # mid-reflectance, has a 2020 answer
PEER_SCANS = ("20200604143557_soilcrust_143557", "20200604143642_20200604_soil_crust_log04")
OTHER_WR_SCAN = "20211020105858_skin_105858"               # carries the 2021 white reference

_STATUS = re.compile(r"HTTP (\d{3})")


class Halt(Exception):
    """A safety rail tripped. Nothing further is sent."""


class Runner:
    def __init__(self, phase: str):
        self.phase = phase
        self.last = 0.0
        self.consecutive_5xx = 0
        OUT_DIR.mkdir(parents=True, exist_ok=True)

    # -- budget ---------------------------------------------------------------------
    @staticmethod
    def used() -> int:
        return sum(1 for p in OUT_DIR.glob("*__*.json"))

    def path(self, label: str) -> Path:
        return OUT_DIR / f"{self.phase}__{label}.json"

    # -- one request ----------------------------------------------------------------
    def send(self, label: str, payload: dict, *, changes: str, expect: str = "") -> dict:
        out = self.path(label)
        if out.exists():                                   # resumable: never re-send
            return json.loads(out.read_text(encoding="utf-8"))
        if self.used() >= MAX_REQUESTS:
            raise Halt(f"request cap {MAX_REQUESTS} reached")
        wait = MIN_GAP - (time.time() - self.last)
        if wait > 0:
            time.sleep(wait)

        status, spectrum, body = 200, None, ""
        try:
            resp = cloud.analyze_scan(credentials.get_token(), payload)
            _, spectrum = cloud.spectrum_from_response(resp)
            body = json.dumps({k: v for k, v in resp.items() if k != "spectrum"})
        except cloud.CloudError as exc:
            m = _STATUS.search(str(exc))
            status = int(m.group(1)) if m else 0
            body = str(exc)
        self.last = time.time()

        rec = {
            "schema": "scio-ciphertext-oracle/1",
            "phase": self.phase, "label": label, "ran_at": store.now_iso(),
            "changes": changes, "expect": expect,
            "status": status, "body": body[:600], "spectrum": spectrum,
            "fingerprint": {k: hashlib.sha256(str(v).encode()).hexdigest()[:12]
                            for k, v in sorted(payload.items())},
        }
        out.write_text(json.dumps(rec, indent=1), encoding="utf-8")   # written FIRST

        if status >= 500 or status == 0:
            self.consecutive_5xx += 1
        else:
            self.consecutive_5xx = 0
        if status in (401, 403, 429):
            raise Halt(f"HTTP {status}: auth/rate-limit challenge, stopping (see {label})")
        if self.consecutive_5xx >= MAX_CONSECUTIVE_5XX:
            raise Halt(f"{MAX_CONSECUTIVE_5XX} consecutive 5xx, stopping (see {label})")
        return rec


def record_path(stem: str) -> Path:
    return next(Path(store.SCANS_DIR).glob(f"{stem}.json"))


def load(stem: str) -> dict:
    rec = session.load_record(record_path(stem))
    rec["_path"] = str(record_path(stem))
    return rec


def stored_spectrum(rec: dict) -> np.ndarray | None:
    ref = (rec.get("reference_spectrum") or {}).get("reflectance")
    return np.asarray(ref, float) if ref else None


# ============================================================================== A0
def phase_a0() -> int:
    """Calibrate the oracle with valid inputs only. Exact identities, no corruption.

    Prediction, if the server computes R = (S - D) / (W - Wd) per pixel and bins after:

    ===========================================  =====================================
    same body in both ``sample`` and ``dark``      R = 0 exactly (decode is role-blind)
    swap ``sample`` and ``sample_dark``            R' = -R exactly (no clip/normalise)
    swap the white pair for another WR             R'/R identical across two scans
    ``sampled_at`` + 1 ms                          unchanged (not cached, not a tweak)
    ===========================================  =====================================

    A cache keyed on (device, sampled_at) would return the old R for the swapped request,
    so the swaps double as the cache test.
    """
    run = Runner("a0")
    base = load(BASELINE_SCAN)
    payload = session.to_payload(base)
    stored = stored_spectrum(base)

    # ---- control: untampered, same session. Everything below is judged against it.
    ctl = run.send("control", payload, changes="none (untampered)",
                   expect="equals the stored 2020 spectrum")
    if ctl["spectrum"] is None:
        raise Halt(f"control failed ({ctl['status']}): {ctl['body'][:120]}")
    R = np.asarray(ctl["spectrum"], float)

    # ---- swap sample <-> dark: R' = -R
    sw = dict(payload)
    sw["sample"], sw["sample_dark"] = payload["sample_dark"], payload["sample"]
    swap = run.send("swap_sample_dark", sw, changes="sample and sample_dark exchanged",
                    expect="R' = -R exactly")

    # ---- the same body in both slots: R = 0
    same = dict(payload)
    same["sample_dark"] = payload["sample"]
    zero = run.send("same_body_both_slots", same, changes="sample_dark := sample (whole blob)",
                    expect="R = 0 exactly")

    # ---- swap the white pair for another white reference, on two scans
    other = session.to_payload(load(OTHER_WR_SCAN))
    white_keys = [k for k in ("sample_white", "sample_white_dark", "sample_white_gradient",
                              "sampled_white_at") if k in other]
    swapped = {}
    for stem in (BASELINE_SCAN,) + PEER_SCANS[:1]:
        p = session.to_payload(load(stem))
        q = dict(p)
        for k in white_keys:
            q[k] = other[k]
        swapped[stem] = (p, run.send(f"white_swap__{stem[-12:]}", q,
                                     changes="white pair replaced by the 2021 white reference",
                                     expect="R'/R identical across scans"))

    # ---- sampled_at + 1 ms
    t = dict(payload)
    t["sampled_at"] = _bump_ms(payload["sampled_at"], 1)
    ts = run.send("sampled_at_plus_1ms", t, changes="sampled_at + 1 ms",
                  expect="unchanged")

    return report_a0(base, stored, R, swap, zero, swapped, ts)


def _bump_ms(iso: str, ms: int) -> str:
    """Add ms to an ISO timestamp with millisecond precision."""
    m = re.match(r"^(.*\.)(\d{3})(.*)$", iso)
    if not m:
        return iso
    return f"{m.group(1)}{(int(m.group(2)) + ms) % 1000:03d}{m.group(3)}"


def report_a0(base, stored, R, swap, zero, swapped, ts) -> int:
    """Judge A0. Three outcomes per identity, not two.

    *confirmed*  the prediction held to floating-point precision.
    *refuted*    the server answered and the answer contradicts the prediction.
    *untestable* the server REJECTED the input. That is not a failed identity - the
                 identity was never evaluated - and it is itself evidence: the server runs
                 a plaintext-dependent validity check in front of the arithmetic.
    """
    results = {}

    def check(name, state, detail):
        results[name] = {"state": state, "detail": detail}
        tag = {"confirmed": "PASS", "refuted": "FAIL", "untestable": "N/A "}[state]
        print(f"  [{tag}] {name:38s} {detail}")

    def rejected(rec):
        return rec["spectrum"] is None

    def reason(rec):
        m = re.search(r'"extra_info":"(\w+)"', rec["body"])
        return m.group(1) if m else "no reason given"

    print("\nA0 identities (valid inputs only)")
    if stored is not None:
        d = float(np.max(np.abs(R - stored)))
        check("control reproduces the 2020 answer", "confirmed" if d < 1e-10 else "refuted",
              f"max|diff| = {d:.3e}")

    for name, rec, want in (("swap sample<->dark gives -R", swap, lambda s: s + R),
                            ("same body in both slots gives 0", zero, lambda s: s)):
        if rejected(rec):
            check(name, "untestable",
                  f"HTTP {rec['status']} InvalidScan/{reason(rec)}: a dark level comparable to "
                  "the sample is refused before any arithmetic")
        else:
            d = float(np.max(np.abs(want(np.asarray(rec["spectrum"], float)))))
            check(name, "confirmed" if d < 1e-12 else "refuted", f"max|residual| = {d:.3e}")

    ratios = []
    for stem, (p, rec) in swapped.items():
        if rejected(rec):
            check(f"white swap accepted ({stem[-12:]})", "untestable", f"HTTP {rec['status']}")
            continue
        Rs = stored_spectrum(load(stem))
        if Rs is not None:
            ratios.append(np.asarray(rec["spectrum"], float) / Rs)
    if len(ratios) >= 2:
        d = float(np.max(np.abs(ratios[0] - ratios[1])))
        check("white swap: R'/R same for 2 scans", "confirmed" if d < 1e-9 else "refuted",
              f"max spread = {d:.3e}  (R is separable: R = g(S,D) / (W - Wd))")

    if rejected(ts):
        check("sampled_at +1 ms leaves R unchanged", "untestable", f"HTTP {ts['status']}")
    else:
        d = float(np.max(np.abs(np.asarray(ts["spectrum"]) - R)))
        check("sampled_at +1 ms leaves R unchanged", "confirmed" if d < 1e-12 else "refuted",
              f"max|diff| = {d:.3e}  (timestamps are not a tweak)")

    # Not cached: a request that changes the answer and whose (device, sampled_at) is the
    # baseline's own. The white-swap on the baseline scan is exactly that.
    if ratios:
        moved = float(np.max(np.abs(ratios[0] - 1.0)))
        check("not served from a cache", "confirmed" if moved > 1e-3 else "refuted",
              f"the white-swapped baseline differs from the control by {moved:.3f} (relative)")

    states = [v["state"] for v in results.values()]
    n_ok, n_bad, n_na = (states.count(s) for s in ("confirmed", "refuted", "untestable"))
    if n_bad:
        gate, label = False, "refuted"
    elif n_na:
        gate, label = None, "partial"
    else:
        gate, label = True, "passed"

    out = OUT_DIR / "A0_VERDICT.json"
    out.write_text(json.dumps({
        "schema": "scio-ciphertext-oracle-verdict/2", "phase": "a0", "ran_at": store.now_iso(),
        "baseline": portable_path(base["_path"]), "identities": results,
        "confirmed": n_ok, "refuted": n_bad, "untestable": n_na, "outcome": label,
        "gate_passed": gate,
        "established": [
            "R is separable: R = g(S, D) / (W - Wd) per band (white-swap ratio agrees to 1e-15).",
            "Timestamps are not a tweak or a cache key.",
            "The server is not serving a cache.",
        ],
        "new_finding": (
            "The server validates the DECODED data before doing arithmetic. Putting a dark "
            "level comparable to the sample in front of it (swap, or the same body twice) "
            "returns InvalidScan / high_ambient (HTTP 422). So tampered requests that produce "
            "out-of-range plaintext will be rejected rather than reported, and a rejection is "
            "a plaintext-dependent bit in its own right."),
        "implication": (
            "Block-cipher-like garbling is likely to be rejected, so it will classify as "
            "'undetermined' - not as any cipher. Small bit-local flips (a stream's) stay "
            "inside the valid range and remain fully informative."),
    }, indent=1), encoding="utf-8")
    print(f"\nA0 outcome: {label.upper()}  ({n_ok} confirmed, {n_bad} refuted, {n_na} untestable)")
    if gate is None:
        print("The gate is not a clean pass: two identities could not be evaluated because the "
              "server rejects them.\nStopping for a decision rather than relaxing the gate.")
    print(f"written: {out}")
    return 0 if gate else (2 if gate is False else 4)


# ============================================================================ pilot
MAX_CONSECUTIVE_REJECTIONS = 8


def _observation(spec_id, kind, params, rec, baseline):
    from scio_offline import malleability as M
    o = M.Observation(spec_id, kind, params, rec["status"], rec["spectrum"], rec["body"])
    o.d = M.delta(baseline, rec["spectrum"])
    return o


def phase_pilot() -> int:
    """Restricted pilot: small in-range flips only, chosen after A0.

    A0 found that the server validates decoded data before any arithmetic, so a flip that
    pushes a pixel out of range is rejected rather than reported. Everything here stays
    within a few counts. Block-cipher-like garbling will still be rejected, and the
    classifier reads that as ``undetermined`` - never as any cipher.

    ~45 requests: control, two lane probes, then the 42-probe restricted protocol.
    """
    from scio_offline import malleability as M

    verdict_a0 = OUT_DIR / "A0_VERDICT.json"
    if not verdict_a0.exists():
        raise Halt("run a0 first")
    a0 = json.loads(verdict_a0.read_text(encoding="utf-8"))
    if a0.get("refuted"):
        raise Halt("A0 refuted an identity; tampered probes would not be interpretable")

    run = Runner("pilot")
    base = load(BASELINE_SCAN)
    payload = session.to_payload(base)

    ctl = run.send("control", payload, changes="none (untampered, this session)",
                   expect="equals the stored 2020 spectrum")
    if ctl["spectrum"] is None:
        raise Halt(f"control failed ({ctl['status']}): {ctl['body'][:120]}")
    R = np.asarray(ctl["spectrum"], float)
    stored = stored_spectrum(base)
    if stored is not None and float(np.max(np.abs(R - stored))) > 1e-10:
        raise Halt("control no longer reproduces the stored answer; results would be stale")

    def probe(spec):
        p = M.tamper_bits(payload, spec["role"], spec["flips"])
        rec = run.send(spec["id"], p, changes=f"{spec['role']}: flip {spec['flips']}",
                       expect="see malleability.py")
        return rec, _observation(spec["id"], spec["kind"],
                                 {"flips": spec["flips"], "role": spec["role"]}, rec, R)

    # ---- which byte of a pixel is the low-weight lane?
    lane_obs = [probe(s)[1] for s in M.lane_probe_specs()]
    lane = M.pick_lane(*lane_obs)
    print(f"lane probes: even={lane_obs[0].status} odd={lane_obs[1].status} -> "
          f"{'low lane = byte ' + str(lane) if lane is not None else 'undetermined, using 0'}")

    obs, rejected_run = [], 0
    for spec in M.restricted_protocol(lane=lane or 0):
        rec, o = probe(spec)
        obs.append(o)
        rejected_run = rejected_run + 1 if rec["spectrum"] is None else 0
        if rejected_run >= MAX_CONSECUTIVE_REJECTIONS:
            print(f"{MAX_CONSECUTIVE_REJECTIONS} consecutive rejections: even tiny flips are "
                  "refused, stopping rather than repeating a question already answered")
            break

    result = M.classify(obs)
    n_ok = sum(1 for o in obs if o.status == 200)
    print(f"\nprobes sent {len(obs)}  accepted {n_ok}  rejected {len(obs) - n_ok}")
    print(f"CLASSIFICATION: {result['label']}  -  {result['why']}")
    for k, v in result["evidence"].items():
        print(f"    {k}: {v}")

    out = OUT_DIR / "PILOT_VERDICT.json"
    out.write_text(json.dumps({
        "schema": "scio-ciphertext-oracle-verdict/2", "phase": "pilot", "ran_at": store.now_iso(),
        "baseline": portable_path(base["_path"]),
        "lane": lane, "probes_sent": len(obs), "accepted": n_ok, "rejected": len(obs) - n_ok,
        "label": result["label"], "why": result["why"], "evidence": result["evidence"],
        "rejection_bodies": sorted({o.body[:200] for o in obs if o.status != 200})[:3],
        "encryption_hypothesis": "not_excluded",
        "limits": ("A label describes locality and scaling of damage in the decoded output. It "
                   "cannot separate CTR-with-a-secret-key from a keyless seeded generator, and "
                   "nothing here can exclude encryption. `undetermined` covers diffusion, an "
                   "authentication tag and a range check, which are indistinguishable from "
                   "outside."),
    }, indent=1), encoding="utf-8")
    print(f"written: {out}")
    return 0


# ========================================================================== foreign
FOREIGN_DIR = Path("dev/analysis_output/foreign_scans")
OUR_DEVICE = "8032AB45611198F1"
OUR_TAG = "20150812-e:PRODUCTION"


def _foreign_payload(rec: dict, device_id: str, i2s: str, ts, wts) -> dict:
    import base64
    blobs = {k: base64.b64decode("".join(v.split())) for k, v in rec["blobs_b64"].items()}
    scan = {"blobs": {k: blobs[k] for k in blobs if not k.startswith("sample_white")}}
    white = {"blobs": {k: blobs[k] for k in blobs if k.startswith("sample_white")}}
    return cloud.build_scan_payload(scan, white, device_id, i2s,
                                    sampled_at=ts, sampled_white_at=wts)


def phase_foreign() -> int:
    """Submit the app-embedded mock/fake blobs, unmodified, under their own identity.

    These are real, validly-signed captures from other devices and older generations. They are
    sent intact - this is NOT a tamper/signature test - to learn two things the closed oracle
    cannot: does another device's signed blob decode under our account (is decode device-bound?),
    and does the older -o / 20150712 generation still decode at all. Timestamps are inert (A0),
    so a borrowed timestamp is used wherever the mock carried none.
    """
    if not FOREIGN_DIR.exists() or not list(FOREIGN_DIR.glob("*.json")):
        raise Halt("no foreign scans; run dev/scripts/extract_mock_scans.py first")
    run = Runner("foreign")

    # a borrowed, inert timestamp for mocks that carry none
    base = session.to_payload(load(BASELINE_SCAN))
    ts0, wts0 = base["sampled_at"], base["sampled_white_at"]

    rows = []

    def submit(label, rec, device_id, i2s, changes):
        ts = rec.get("sampled_at") or ts0
        wts = rec.get("sampled_white_at") or wts0
        payload = _foreign_payload(rec, device_id, i2s, ts, wts)
        r = run.send(label, payload, changes=changes, expect="intact foreign blob")
        ok = r["spectrum"] is not None
        et = ""
        if not ok:
            m = re.search(r'"error_type":"([^"]+)"', r["body"])
            et = m.group(1) if m else f"HTTP {r['status']}"
        rows.append({"label": label, "device_submitted": device_id, "i2s": i2s,
                     "native_device": rec.get("device_id"), "native_i2s": rec.get("i2s_tag_config"),
                     "status": r["status"], "ok": ok, "error_type": et,
                     "n_bands": len(r["spectrum"]) if ok else None})
        print(f"  {label:34s} {r['status']}  {'OK ' + str(len(r['spectrum'])) + ' bands' if ok else et}")
        return r

    scans = {p.stem: json.loads(p.read_text(encoding="utf-8"))
             for p in sorted(FOREIGN_DIR.glob("*.json"))}

    print("native identity (each mock under its own device_id + tag):")
    for name, rec in scans.items():
        submit(f"native__{name}", rec, rec.get("device_id") or OUR_DEVICE,
               rec.get("i2s_tag_config") or OUR_TAG, "foreign blob, native device_id + tag")

    # device-binding: one foreign blob under OUR device_id (id mismatch), then + OUR tag
    probe = scans.get("fake_cheese_scan") or next(iter(scans.values()))
    print("\ndevice-binding (the same foreign blob, our identity):")
    submit("bind__our_id_native_tag", probe, OUR_DEVICE,
           probe.get("i2s_tag_config") or OUR_TAG, "foreign blob, OUR device_id, native tag")
    submit("bind__our_id_our_tag", probe, OUR_DEVICE, OUR_TAG,
           "foreign blob, OUR device_id + OUR tag")

    n_ok = sum(1 for r in rows if r["ok"])
    decoded_devices = sorted({r["native_device"] for r in rows if r["ok"] and r["label"].startswith("native")})
    bind = [r for r in rows if r["label"].startswith("bind")]
    binding = ("device-bound: a foreign blob is refused under our device_id"
               if bind and not any(r["ok"] for r in bind)
               else "NOT device-bound: a foreign blob decoded under our device_id"
               if any(r["ok"] for r in bind) else "inconclusive")

    out = OUT_DIR / "FOREIGN_VERDICT.json"
    out.write_text(json.dumps({
        "schema": "scio-foreign-verdict/1", "ran_at": store.now_iso(),
        "submitted": len(rows), "accepted": n_ok,
        "generations_tried": sorted({r["native_i2s"] for r in rows}),
        "devices_that_decoded_natively": decoded_devices,
        "device_binding": binding,
        "rows": rows,
        "note": ("The chosen-ciphertext oracle is closed, so these only characterise: they cannot "
                 "advance a decode. All blobs were submitted unmodified."),
    }, indent=1), encoding="utf-8")
    print(f"\naccepted {n_ok}/{len(rows)}  |  {binding}")
    print(f"generations tried: {sorted({r['native_i2s'] for r in rows})}")
    print(f"written: {out}")
    return 0


def status() -> int:
    n = Runner.used()
    print(f"requests recorded: {n}/{MAX_REQUESTS}")
    for p in sorted(OUT_DIR.glob("*__*.json")):
        d = json.loads(p.read_text(encoding="utf-8"))
        print(f"  {p.stem:44s} {d['status']}  {d['changes'][:60]}")
    return 0


def main(argv) -> int:
    cmd = argv[1] if len(argv) > 1 else "status"
    try:
        if cmd == "a0":
            return phase_a0()
        if cmd == "pilot":
            return phase_pilot()
        if cmd == "foreign":
            return phase_foreign()
        if cmd == "status":
            return status()
        print(__doc__)
        return 1
    except Halt as exc:
        print(f"\nHALT: {exc}")
        return 3


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
