"""Canonical, read-only inventory of locally available SCIO observations."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterable

from . import store
from .paths import portable_path


@dataclass
class CorpusRecord:
    record_id: str
    path: str
    source: str
    label: str
    blobs: dict[str, bytes] = field(repr=False)
    device: dict = field(default_factory=dict)
    sampled_at: str | None = None
    calibration_id: str | None = None
    spectrum: list[float] | None = field(default=None, repr=False)
    wavelengths: list[float] | None = field(default=None, repr=False)
    warnings: list[str] = field(default_factory=list)

    def index_row(self) -> dict:
        row = asdict(self)
        row.pop("blobs", None)
        row.pop("spectrum", None)
        row.pop("wavelengths", None)
        row["blob_sizes"] = {k: len(v) for k, v in self.blobs.items()}
        row["blob_sha256"] = {k: hashlib.sha256(v).hexdigest() for k, v in self.blobs.items()}
        row["spectrum_points"] = len(self.spectrum) if self.spectrum is not None else None
        row["wavelength_points"] = len(self.wavelengths) if self.wavelengths is not None else None
        return row


def _label(path: Path, meta: dict) -> str:
    for key in ("target_label", "material", "label", "name", "sample_name"):
        if meta.get(key):
            return str(meta[key])
    if path.parent.name not in {"log_extracted", "scan_json", "scan_json_calibration"}:
        return path.parent.name
    stem = path.stem.lower()
    for token in ("burst", "hand", "skin", "wood", "mirror", "dark", "calibration"):
        if token in stem:
            return token
    return path.stem


def _spectrum_and_axis(meta: dict, loaded_spectrum) -> tuple[list[float] | None, list[float] | None]:
    spectrum = loaded_spectrum
    if isinstance(spectrum, dict):
        spectrum = spectrum.get("spectrum") or spectrum.get("values")
    if spectrum is not None:
        try:
            spectrum = [float(x) for x in spectrum]
        except (TypeError, ValueError):
            spectrum = None
    wavelengths = meta.get("wavelengths")
    if isinstance(wavelengths, dict):
        start = wavelengths.get("start")
        step = wavelengths.get("steps", wavelengths.get("step"))
        count = wavelengths.get("num_WL", wavelengths.get("count"))
        if start is not None and step is not None and count:
            wavelengths = [float(start) + i * float(step) for i in range(int(count))]
        else:
            wavelengths = None
    if isinstance(wavelengths, list):
        wavelengths = [float(x) for x in wavelengths]
    elif spectrum is not None and len(spectrum) == 331:
        wavelengths = [float(x) for x in range(740, 1071)]
    else:
        wavelengths = None
    return spectrum, wavelengths


def load_record(path, source: str | None = None) -> CorpusRecord:
    path = Path(path)
    if "log_extracted" in path.parts:
        loaded = store.load_fixture(path)
        source = source or "app_log_fixture"
    else:
        loaded = store.load_scan(path)
        source = source or ("white_reference" if "calibration" in path.name.lower() else "capture")
    meta = loaded["meta"]
    blobs = loaded["blobs"]
    digest = hashlib.sha256()
    for name in sorted(blobs):
        digest.update(name.encode("ascii"))
        digest.update(blobs[name])
    spectrum, wavelengths = _spectrum_and_axis(meta, loaded.get("spectrum"))
    warnings = []
    if not blobs:
        warnings.append("no scan blobs found")
    if spectrum is not None and len(spectrum) != 331:
        warnings.append(f"unexpected archived spectrum length {len(spectrum)}")
    return CorpusRecord(
        record_id=digest.hexdigest()[:20] if blobs else hashlib.sha256(str(path).encode()).hexdigest()[:20],
        path=portable_path(path), source=source, label=_label(path, meta), blobs=blobs,
        device=loaded.get("device", {}),
        sampled_at=meta.get("sampled_at") or meta.get("sampled_white_at"),
        calibration_id=(portable_path(meta["calibration_file"])
                        if meta.get("calibration_file") else meta.get("sampled_white_at")),
        spectrum=spectrum, wavelengths=wavelengths, warnings=warnings,
    )


def discover_json(roots: Iterable[str | Path]) -> list[Path]:
    """Find candidate JSON records, excluding generated reports and metadata."""
    paths = set()
    for root in roots:
        p = Path(root)
        if p.is_file() and p.suffix.lower() == ".json":
            paths.add(p.resolve())
        elif p.exists():
            for candidate in p.rglob("*.json"):
                if candidate.name.endswith("_report.json") or "device_files" in candidate.parts:
                    continue
                paths.add(candidate.resolve())
    return sorted(paths)


def build_corpus(roots: Iterable[str | Path]) -> tuple[list[CorpusRecord], list[dict]]:
    records, errors = [], []
    for path in discover_json(roots):
        try:
            rec = load_record(path)
            if rec.blobs:
                records.append(rec)
        except Exception as exc:  # corpus construction must report, not hide, malformed inputs
            errors.append({"path": portable_path(path), "error": f"{type(exc).__name__}: {exc}"})
    return records, errors


def write_index(records: list[CorpusRecord], path, errors: list[dict] | None = None) -> Path:
    """Write provenance and hashes only; never duplicate or alter raw bytes."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"schema": "scio-corpus-index/1", "records": [r.index_row() for r in records],
               "errors": errors or []}
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path
