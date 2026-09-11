#!/usr/bin/env python
"""Does the i2s tag change how the server decodes a *fixed* scan?

The question, and why it matters
-------------------------------
The i2s tag (``i2s_tag_config``, which Consumer Physics' own firmware endpoint
calls ``compression_version``) selects the image-to-spectrum generation: which
``centers``/``bins``/``nPixelsPerBin`` tables apply, and which reconstruction
algorithm the server runs. The client never validates or parses it - it is an
opaque 64-byte string read from the device and passed through - so we can send
any tag we like with otherwise byte-identical blobs.

If the server returns a *different* spectrum for the same ciphertext under a
different tag, that is a **chosen-binning oracle**: each spectrum is a different
projection of the same hidden pixel vector. That would be a qualitatively new
handle on the offline problem, because it attacks the binning stage (after
decryption) rather than the key.

Three outcomes are possible, and all three are results:

1. **Rejected** - the server validates tag against device/data. No oracle.
2. **Identical spectra** - the tag is not in the analysis path at all (only in
   the firmware path). No oracle, but it settles what the tag does.
3. **Different spectra** - an oracle exists. Then the question is how much it
   constrains the hidden pixels; see ``analyse`` output.

Method
------
One canonical record is held fixed; only ``i2s_tag_config`` varies. The control
tag is sent **twice, non-adjacently** first, because without a determinism check
any observed difference could be server-side noise rather than the tag.

    python dev/scripts/i2s_tag_oracle.py              # run, 20 s apart
    python dev/scripts/i2s_tag_oracle.py --analyse    # just re-analyse results
    python dev/scripts/i2s_tag_oracle.py --scan <path>

Results are one JSON per (scan, tag) under dev/analysis_output/i2s_tag_oracle/,
resumable - anything already recorded is skipped.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import _bootstrap  # noqa: F401  (sets sys.path + cwd to the repo root)

from scio import cloud, credentials, session, store  # noqa: E402
from scio.paths import portable_path  # noqa: E402

OUT_DIR = Path("dev/analysis_output/i2s_tag_oracle")
PAUSE_DEFAULT = 20.0

# Every tag literal observed anywhere, plus bounded probes of the letter slot.
# Provenance matters: a tag the apps actually used is far more likely to be
# server-recognised than one we invented.
TAGS = [
    ("control",        "20150812-e:PRODUCTION",  "this device's real tag (from its BLE-ID)"),
    ("control_repeat", "20150812-e:PRODUCTION",  "same tag again - determinism check"),
    ("letter_o",       "20150812-o:PRODUCTION",  "ScioMockDevice in consumer 1.3.8.554 / Lab 1.3.12.144"),
    ("no_letter",      "20150812:PRODUCTION",    "ScioMockDevice in 1.1.0.320 / 1.2.6.476 / researcher 2017"),
    ("older_date",     "20150712:PRODUCTION",    "FakeJson.FAKE_WHITE_CHOCOLATE_SCAN - a different generation"),
    ("letter_a",       "20150812-a:PRODUCTION",  "probe: unobserved letter, same date"),
    ("empty",          "",                       "known-bad control: server rejects an empty tag"),
    ("garbage",        "not-a-tag",              "known-bad control: maps the validation surface"),
]


def _arg(name, default=None):
    a = sys.argv[1:]
    for i, x in enumerate(a):
        if x == name and i + 1 < len(a):
            return a[i + 1]
        if x.startswith(name + "="):
            return x.split("=", 1)[1]
    return default


def pick_scans() -> list[Path]:
    """Prefer records that carry the server's 2020/2021 spectrum as ground truth."""
    explicit = _arg("--scan")
    if explicit:
        return [Path(explicit)]
    with_ref, without = [], []
    for p in sorted(Path(store.SCANS_DIR).glob("*.json")):
        rec = session.load_record(p)
        if not rec.get("white_reference"):
            continue
        (with_ref if rec.get("reference_spectrum") else without).append(p)
    # two scans: enough to tell a tag effect from a per-scan quirk
    return (with_ref[:1] + without[:1]) or with_ref[:2] or without[:2]


def run_one(rec: dict, label: str, tag: str, note: str, out: Path) -> dict:
    payload = session.to_payload(rec)
    payload["i2s_tag_config"] = tag          # the single variable
    resp = wl = refl = None
    error = None
    try:
        resp = cloud.analyze_scan(credentials.get_token(), payload)
        wl, refl = cloud.spectrum_from_response(resp)
    except cloud.CloudError as exc:
        error = str(exc)

    record = {
        "schema": "scio-i2s-oracle/1",
        "ran_at": store.now_iso(),
        "tag_label": label,
        "i2s_tag_config": tag,
        "tag_provenance": note,
        # portable: SCANS_DIR is absolute, so str() would leak a home path
        "source_record": portable_path(rec.get("_path")),
        "scan_uid": rec.get("scan_uid"),
        "device_id": rec.get("device", {}).get("device_id"),
        "sampled_at": rec.get("sampled_at"),
        # proof the input really was byte-identical apart from the tag
        "payload_fingerprint": {
            k: (len(v) if isinstance(v, str) and k.startswith("sample") else v)
            for k, v in sorted(payload.items())
        },
        "response": resp,
        "error": error,
        "spectrum": {"wavelength_nm": wl, "reflectance": refl} if refl else None,
        "reference_spectrum": (rec.get("reference_spectrum") or {}).get("reflectance"),
    }
    out.write_text(json.dumps(record, indent=1), encoding="utf-8")
    return record


def analyse() -> int:
    # Only this experiment's own records - the directory also holds the
    # firmware-endpoint probe, which has a different shape.
    rows = []
    for p in sorted(OUT_DIR.glob("*.json")):
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except ValueError:
            continue
        if isinstance(d, dict) and d.get("schema") == "scio-i2s-oracle/1":
            rows.append(d)
    if not rows:
        print("No results yet - run without --analyse first.")
        return 1

    by_scan: dict[str, list[dict]] = {}
    for r in rows:
        by_scan.setdefault(r["scan_uid"] or r["source_record"], []).append(r)

    print(f"\n{len(rows)} request(s) across {len(by_scan)} scan(s)\n")
    summary = {"per_scan": [], "conclusion": None}
    oracle_found = False

    for uid, group in by_scan.items():
        group.sort(key=lambda r: r["tag_label"])
        ctrl = next((r for r in group if r["tag_label"] == "control" and r["spectrum"]), None)
        rep = next((r for r in group if r["tag_label"] == "control_repeat" and r["spectrum"]), None)
        print(f"scan {uid}  ({group[0]['sampled_at']})")

        # Determinism first: without it, no difference below means anything.
        noise = None
        if ctrl and rep:
            noise = max(abs(a - b) for a, b in zip(ctrl["spectrum"]["reflectance"],
                                                   rep["spectrum"]["reflectance"]))
            print(f"  determinism (control vs control_repeat): max|diff| = {noise:.3e}"
                  f"  -> server is {'deterministic' if noise == 0 else 'NOT bit-deterministic'}")
        else:
            print("  determinism: not measurable (a control did not return a spectrum)")

        if ctrl and ctrl.get("reference_spectrum"):
            d = max(abs(a - b) for a, b in zip(ctrl["spectrum"]["reflectance"],
                                               ctrl["reference_spectrum"]))
            print(f"  control vs stored 2020/21 spectrum:      max|diff| = {d:.3e}")

        print(f"  {'tag':24s} {'result':28s} {'max|diff| vs control':>22s}")
        print("  " + "-" * 78)
        for r in group:
            if r["error"]:
                res = "ERROR " + r["error"][:60].replace("\n", " ")
                diff = "-"
            elif r["spectrum"] and ctrl:
                dv = max(abs(a - b) for a, b in zip(r["spectrum"]["reflectance"],
                                                    ctrl["spectrum"]["reflectance"]))
                res = f"OK {len(r['spectrum']['reflectance'])} pts"
                diff = f"{dv:.3e}"
                if r["tag_label"] not in ("control", "control_repeat") and \
                        noise is not None and dv > max(noise * 10, 1e-12):
                    oracle_found = True
                    diff += "  <-- DIFFERS"
            else:
                res, diff = "no spectrum", "-"
            print(f"  {(r['i2s_tag_config'] or '<empty>'):24s} {res:28s} {diff:>22s}")
        print()
        summary["per_scan"].append({
            "scan": uid, "determinism_max_diff": noise,
            "tags": [{"tag": r["i2s_tag_config"], "label": r["tag_label"],
                      "ok": r["spectrum"] is not None, "error": r["error"]} for r in group],
        })

    accepted = {r["i2s_tag_config"] for r in rows if r["spectrum"]}
    rejected = {r["i2s_tag_config"]: r["error"] for r in rows if r["error"]}
    print("=" * 80)
    print(f"tags accepted: {sorted(accepted)}")
    for t, e in sorted(rejected.items()):
        print(f"tag rejected:  {t!r} -> {e[:90]}")
    print()
    if oracle_found:
        summary["conclusion"] = (
            "DIFFERENT spectra for the same ciphertext under different tags: a "
            "chosen-binning oracle exists. Next step is to quantify how much it "
            "constrains the hidden pixel vector.")
        print("RESULT: the tag CHANGES the decode. A chosen-binning oracle exists -")
        print("        each accepted tag is a different projection of the same pixels.")
    elif len(accepted) > 1:
        summary["conclusion"] = (
            "Several tags accepted but every spectrum is identical to the control: "
            "the tag is NOT in the analysis path, so it yields no oracle. It is used "
            "only on the firmware endpoints, to decide which tables a device holds.")
        print("RESULT: multiple tags accepted, all spectra identical ->")
        print("        the tag does NOT affect analysis. No oracle. Negative result.")
    else:
        summary["conclusion"] = (
            "Only the device's own tag is accepted; every substitute is rejected. "
            "The server validates the tag, so no chosen-binning oracle is reachable "
            "through this endpoint.")
        print("RESULT: only the device's own tag is accepted -> no oracle this way.")
    (OUT_DIR / "SUMMARY.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
    return 0


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    if "--analyse" in sys.argv[1:]:
        return analyse()

    pause = float(_arg("--pause", PAUSE_DEFAULT))
    scans = pick_scans()
    if not scans:
        print("No processable canonical records found.")
        return 1

    jobs = []
    for p in scans:
        rec = session.load_record(p)
        rec["_path"] = str(p)
        for label, tag, note in TAGS:
            out = OUT_DIR / f"{p.stem}__{label}.json"
            if not out.exists():
                jobs.append((rec, label, tag, note, out))

    print(f"{len(scans)} scan(s) x {len(TAGS)} tags; {len(jobs)} request(s) to make "
          f"({pause:.0f}s apart, ~{len(jobs) * pause / 60:.1f} min).")
    for p in scans:
        print(f"  scan: {p.name}")
    print()

    for i, (rec, label, tag, note, out) in enumerate(jobs, 1):
        r = run_one(rec, label, tag, note, out)
        status = (f"OK {len(r['spectrum']['reflectance'])} pts" if r["spectrum"]
                  else f"ERROR {(r['error'] or '')[:70]}")
        print(f"[{i:2d}/{len(jobs)}] {label:16s} {(tag or '<empty>'):24s} {status}")
        if i < len(jobs):
            time.sleep(pause)

    print()
    return analyse()


if __name__ == "__main__":
    raise SystemExit(main())
