"""Conservative spectral output and validation interfaces.

This module intentionally has no default opaque-payload decoder. A transform
must first be registered with evidence and pass the validation gates below.
"""

from __future__ import annotations

import csv
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable

import numpy as np

from .decode import normalize_curve, wavelength_axis


@dataclass
class DecoderProfile:
    name: str
    version: str
    device_id: str
    i2s_tag: str | None
    evidence_report: str
    validated: bool = False


@dataclass
class DecodedSpectrum:
    wavelength_nm: list[float]
    normalized: list[float]
    intensity: list[float] | None = None
    reflectance: list[float] | None = None
    quality_flags: list[str] = field(default_factory=list)
    provenance: dict = field(default_factory=dict)

    def validate(self) -> None:
        n = len(self.wavelength_nm)
        if n < 2 or len(self.normalized) != n:
            raise ValueError("wavelength and normalized arrays must have equal length >= 2")
        if any(b <= a for a, b in zip(self.wavelength_nm, self.wavelength_nm[1:])):
            raise ValueError("wavelengths must be strictly increasing")
        for name in ("intensity", "reflectance"):
            values = getattr(self, name)
            if values is not None and len(values) != n:
                raise ValueError(f"{name} length does not match wavelength axis")


def make_spectrum(values, *, wavelengths=None, profile: DecoderProfile,
                  provenance: dict | None = None, normalization: str = "robust",
                  value_kind: str = "intensity") -> DecodedSpectrum:
    """Wrap output from a *validated* transform; refuse speculative curves."""
    if not profile.validated:
        raise RuntimeError("decoder profile is not validated; refusing to label output as a spectrum")
    values = np.asarray(values, dtype=float)
    wl = wavelength_axis(count=len(values)) if wavelengths is None else np.asarray(wavelengths, dtype=float)
    normalized = normalize_curve(values, normalization)
    kwargs = {"intensity": None, "reflectance": None}
    if value_kind not in kwargs:
        raise ValueError("value_kind must be intensity or reflectance")
    kwargs[value_kind] = values.tolist()
    result = DecodedSpectrum(
        wavelength_nm=wl.tolist(), normalized=normalized.tolist(), **kwargs,
        provenance={**(provenance or {}), "decoder": asdict(profile)},
    )
    result.validate()
    return result


def decode_scan(scan, calibration, profile: DecoderProfile,
                transform: Callable[[dict, dict], np.ndarray]) -> DecodedSpectrum:
    """Public decoding entry point, gated by a validated decoder profile."""
    values = transform(scan, calibration)
    return make_spectrum(values, profile=profile,
                         provenance={"scan": scan.get("path"), "calibration": calibration.get("path")})


def spectral_angle(a, b) -> float:
    a, b = np.asarray(a, float), np.asarray(b, float)
    denom = np.linalg.norm(a) * np.linalg.norm(b)
    if denom == 0:
        return float("nan")
    return float(np.arccos(np.clip(np.dot(a, b) / denom, -1.0, 1.0)))


def compare_curves(a, b) -> dict:
    """Metrics used by the repeatability and held-out spectral gates."""
    a, b = np.asarray(a, float), np.asarray(b, float)
    if a.shape != b.shape or a.ndim != 1 or a.size < 3:
        raise ValueError("curves must be equal-length one-dimensional arrays")
    mask = np.isfinite(a) & np.isfinite(b)
    if mask.sum() < 3:
        return {"pearson_r": float("nan"), "spectral_angle_rad": float("nan")}
    an, bn = normalize_curve(a[mask], "l2"), normalize_curve(b[mask], "l2")
    return {"pearson_r": float(np.corrcoef(a[mask], b[mask])[0, 1]),
            "spectral_angle_rad": spectral_angle(an, bn)}


def acceptance(metrics: list[dict], kind: str) -> dict:
    """Apply the documented minimum gates to a collection of comparisons."""
    if kind not in {"replicate", "reference"}:
        raise ValueError("kind must be replicate or reference")
    threshold_r = 0.98 if kind == "replicate" else 0.90
    threshold_angle = 0.10 if kind == "replicate" else None
    rs = [m["pearson_r"] for m in metrics if np.isfinite(m.get("pearson_r", np.nan))]
    angles = [m["spectral_angle_rad"] for m in metrics
              if np.isfinite(m.get("spectral_angle_rad", np.nan))]
    median_r = float(np.median(rs)) if rs else float("nan")
    median_angle = float(np.median(angles)) if angles else float("nan")
    passed = bool(rs and median_r >= threshold_r)
    if threshold_angle is not None:
        passed = passed and bool(angles and median_angle <= threshold_angle)
    return {"kind": kind, "passed": passed, "median_pearson_r": median_r,
            "median_spectral_angle_rad": median_angle,
            "required_pearson_r": threshold_r,
            "maximum_angle_rad": threshold_angle}


def export_spectrum(spectrum: DecodedSpectrum, path) -> Path:
    spectrum.validate()
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.suffix.lower() == ".json":
        path.write_text(json.dumps(asdict(spectrum), indent=2), encoding="utf-8")
    elif path.suffix.lower() == ".csv":
        with path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["wavelength_nm", "normalized", "intensity", "reflectance"])
            for i, wl in enumerate(spectrum.wavelength_nm):
                writer.writerow([wl, spectrum.normalized[i],
                                 spectrum.intensity[i] if spectrum.intensity else "",
                                 spectrum.reflectance[i] if spectrum.reflectance else ""])
    else:
        raise ValueError("output must end in .json or .csv")
    return path
