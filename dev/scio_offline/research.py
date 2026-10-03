"""Auditable research records and numerical validation, independent of production."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from scio import session, store

ROOT = Path(__file__).resolve().parents[2]
DEV = ROOT / "dev"


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def label(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return "<external>/" + path.name


def write_new(path, data):
    path = Path(path).resolve()
    if not path.is_relative_to(DEV):
        raise ValueError("research outputs must be below dev")
    def convert(value):
        if isinstance(value, np.ndarray): return value.tolist()
        if isinstance(value, np.generic): return value.item()
        raise TypeError('unsupported report value: '+type(value).__name__)
    serialized = json.dumps(data, indent=2, allow_nan=False, default=convert)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as f:
        f.write(serialized + "\n")
    return path


def snapshot():
    """Hash every source-data and production file; no contents in report."""
    result = {}
    for folder in ("src", "tests", "tools", "01_rawdata", "02_processed_data"):
        for p in sorted((ROOT / folder).rglob("*")):
            if p.is_file() and "__pycache__" not in p.parts and ".ipynb_checkpoints" not in p.parts:
                result[label(p)] = sha(p.read_bytes())
    return result


def contexts():
    rows = []
    for p in sorted((ROOT / "02_processed_data").glob("*_spectrum.json")):
        d = json.loads(p.read_text(encoding="utf-8"))
        rec = d.get("scan")
        if not rec or not d.get("spectrum", {}).get("reflectance"):
            continue
        sample, white = session.record_blobs(rec)
        device = rec.get("device", {})
        rows.append({"source": label(p), "record": rec, "device": device,
                     "blobs": {**sample, **white}, "truth": d["spectrum"],
                     "id": sha(b"".join(k.encode() + v for k, v in sorted({**sample, **white}.items()))),
                     "white_group": sha(b"".join(v for _, v in sorted(white.items()))),
                     "acquisition_group": str(rec.get("sampled_at", ""))[:10]})
    return rows


def manifest():
    files, blobs = [], {}
    for folder in ("01_rawdata", "02_processed_data", "dev/analysis_output/foreign_scans"):
        for p in sorted((ROOT / folder).rglob("*")):
            if not p.is_file():
                continue
            raw = p.read_bytes()
            files.append({"path": label(p), "bytes": len(raw), "sha256": sha(raw)})
            if p.suffix != ".json":
                continue
            try:
                d = json.loads(raw)
                if not isinstance(d, dict):
                    continue
                rec = d.get("scan", d)
                if rec.get("schema") == "scio-scan/2":
                    s, w = session.record_blobs(rec)
                    values, meta = {**s, **w}, rec.get("device", {})
                elif "foreign_scans" in p.parts:
                    import base64
                    values = {k: base64.b64decode(v) for k, v in rec.get('blobs_b64', {}).items()
                              if k in store.SCAN_KEYS + store.WHITE_KEYS and isinstance(v, str)}
                    meta = rec
                else:
                    loaded = store.load_fixture(p) if "log_extracted" in p.parts else store.load_scan(p)
                    values, meta = loaded.get("blobs", {}), loaded.get("device", {})
                for role, value in values.items():
                    digest = sha(value)
                    item = blobs.setdefault(digest, {"bytes": len(value), "occurrences": []})
                    item["occurrences"].append({"source": label(p), "role": role,
                        "device_id": meta.get("device_id"), "i2s_tag": meta.get("i2s_tag_config"),
                        "firmware": meta.get("firmware_version")})
            except (ValueError, TypeError, KeyError):
                continue
    pairs = contexts()
    # Connected components prevent both acquisition and shared-WR leakage.
    components = []
    for row in pairs:
        links = {"white:" + row["white_group"], "day:" + row["acquisition_group"]}
        matched = [c for c in components if c["links"] & links]
        new = {"links": links, "ids": [row["id"]]}
        for c in matched:
            new["links"].update(c["links"]); new["ids"].extend(c["ids"]); components.remove(c)
        components.append(new)
    components.sort(key=lambda c: sha("|".join(sorted(c["links"])).encode()))
    # Exact subset closest to 25%, excluding empty/all partitions.
    choices = {0: []}
    for i, c in enumerate(components):
        for n, selected in list(choices.items()):
            choices.setdefault(n + len(c["ids"]), selected + [i])
    candidates = [n for n in choices if 0 < n < len(pairs)]
    chosen = choices[min(candidates, key=lambda n: (abs(n - len(pairs)*.25), n))] if candidates else []
    confirmation = [x for i in chosen for x in components[i]["ids"]]
    return {"schema": "scio-research-manifest/1", "files": files, "blobs": blobs,
        "pairs": [{**{k: r[k] for k in ("source", "id", "white_group", "acquisition_group")},
                   "device_id":r['device'].get('device_id'),"i2s_tag":r['device'].get('i2s_tag_config'),
                   "firmware_version":r['device'].get('firmware_version'),
                   "blob_sha256":{role:sha(blob) for role,blob in r['blobs'].items()}} for r in pairs],
        "confirmation_ids": confirmation, "confirmation_fraction": len(confirmation)/max(1,len(pairs)),
        "split_limit": "All existing records were previously examined. This is a frozen retrospective "
                       "confirmation split; new captures are required for genuinely unseen validation.",
        "components": [{"links": sorted(c["links"]), "ids": c["ids"]} for c in components]}


@dataclass
class DecodeInput:
    blobs: dict[str, bytes]
    device_id: str
    i2s_tag: str
    firmware_version: int | None = None
    calibration_artifacts: dict[str, bytes] = field(default_factory=dict)


@dataclass
class DecodeResult:
    wavelength_nm: list[float]
    reflectance: list[float]
    intermediate: dict[str, bytes] = field(default_factory=dict)
    intermediate_layout: str | None = None
    sample_domain: list[float] | None = None
    white_domain: list[float] | None = None
    domain_evidence: str | None = None
    quality_flags: list[str] = field(default_factory=list)


def numerical_check(result: DecodeResult, truth: dict):
    if result.quality_flags:
        return {"passed": False, "reason": "decoder quality flags present", "flags":result.quality_flags}
    axis = np.asarray(result.wavelength_nm, float)
    expected_axis = np.asarray(truth["wavelength_nm"], float)
    a, b = np.asarray(result.reflectance, float), np.asarray(truth["reflectance"], float)
    if axis.shape != (331,) or a.shape != (331,) or b.shape != (331,):
        return {"passed": False, "reason": "requires 331 bands"}
    if not np.isfinite(a).all() or not np.isfinite(b).all() or not np.isfinite(axis).all() or not np.array_equal(axis, expected_axis):
        return {"passed": False, "reason": "nonfinite values or incorrect wavelength axis"}
    for vector in (result.sample_domain, result.white_domain):
        if vector is not None and (not result.domain_evidence or np.asarray(vector).shape != (331,) or not np.isfinite(vector).all()):
            return {"passed": False, "reason": "unsupported domain vector claim"}
    err = np.abs(a-b)
    return {"passed": bool(np.allclose(a,b,atol=1e-6,rtol=1e-6)),
            "strict_1e_10": bool(np.allclose(a,b,atol=1e-10,rtol=1e-10)),
            "max_absolute_error": float(err.max()), "rmse": float(np.sqrt(np.mean(err**2))),
            "per_band_absolute_error": err.tolist(),
            "per_band_relative_error_floor_1e_12": (err/np.maximum(np.abs(b),1e-12)).tolist(),
            "max_relative_error_floor_1e_12": float((err/np.maximum(np.abs(b),1e-12)).max())}


def validate_decoder(decoder, rows, supported, artifacts=None):
    """Truth never enters DecodeInput. In-scope failures cannot be hidden by median."""
    results = []
    for row in rows:
        d = row["device"]
        scope = (d.get("device_id"), d.get("i2s_tag_config"))
        if scope not in supported:
            continue
        inp = DecodeInput(dict(row["blobs"]), *scope, d.get("firmware_version"), artifacts or {})
        try:
            result = decoder(inp)
            check = numerical_check(result, row["truth"])
        except Exception as exc:
            check = {"passed": False, "reason": type(exc).__name__}
        results.append({"id": row["id"], **check})
    return {"passed": bool(results) and all(r["passed"] for r in results), "per_scan": results,
            "limits": "Numerical agreement alone cannot exclude memorization; require new captures, "
                      "implementation review and input-sensitivity tests before claiming a decoder."}
