"""Load archived server spectral-domain CSVs without treating them as plaintext packets."""

from __future__ import annotations

import csv
import math
from dataclasses import dataclass
from pathlib import Path

from .paths import portable_path


@dataclass
class ReferenceTable:
    path: str
    header_row: int
    rows: int
    metadata_columns: list[str]
    axes: dict[str, list[float]]


def _read_table(path):
    rows = list(csv.reader(Path(path).open(encoding="utf-8-sig", newline="")))
    header_i = next((i for i, row in enumerate(rows)
                     if any(cell.strip().startswith(("spectrum_", "band740")) for cell in row)), None)
    if header_i is None:
        raise ValueError("no wavelength column header found")
    return rows, header_i, [cell.strip() for cell in rows[header_i]]


def inspect_reference_csv(path) -> ReferenceTable:
    """Find spectrum/wr_raw/sample_raw columns in a possibly prefaced CSV."""
    path = Path(path)
    rows, header_i, header = _read_table(path)
    axes = {"spectrum": [], "wr_raw": [], "sample_raw": []}
    spectral_columns = set()
    for i, name in enumerate(header):
        if name.startswith("band") and name[4:].replace(".", "", 1).isdigit():
            axes["spectrum"].append(float(name[4:])); spectral_columns.add(i)
        for prefix in tuple(axes):
            marker = prefix + "_"
            if name.startswith(marker):
                try:
                    axes[prefix].append(float(name[len(marker):])); spectral_columns.add(i)
                except ValueError:
                    pass
    axes = {k: v for k, v in axes.items() if v}
    metadata = [name for i, name in enumerate(header) if i not in spectral_columns and name]
    spectral_indices = sorted(spectral_columns)
    def is_numeric_data(row):
        for i in spectral_indices[:1]:
            try:
                float(row[i])
                return True
            except (ValueError, IndexError):
                return False
        return False
    data_rows = sum(is_numeric_data(row) for row in rows[header_i + 1:])
    return ReferenceTable(portable_path(path), header_i, data_rows, metadata, axes)


def validate_spectral_ratio(path) -> dict:
    """Test whether archived spectrum = sample_raw / wr_raw wavelength-wise."""
    rows, header_i, header = _read_table(path)
    groups = {}
    for prefix in ("spectrum_", "sample_raw_", "wr_raw_"):
        groups[prefix] = {name[len(prefix):]: i for i, name in enumerate(header)
                          if name.startswith(prefix)}
    common = sorted(set(groups["spectrum_"]) & set(groups["sample_raw_"]) & set(groups["wr_raw_"]),
                    key=float)
    if not common:
        return {"tested": False, "reason": "required spectral-domain columns not present"}
    errors, rows_tested, points = [], 0, 0
    for row in rows[header_i + 1:]:
        row_errors = []
        for wl in common:
            try:
                spectrum = float(row[groups["spectrum_"][wl]])
                sample = float(row[groups["sample_raw_"][wl]])
                white = float(row[groups["wr_raw_"][wl]])
            except (ValueError, IndexError):
                continue
            if not white or not all(math.isfinite(x) for x in (spectrum, sample, white)):
                continue
            row_errors.append(abs(spectrum - sample / white))
        if row_errors:
            rows_tested += 1
            points += len(row_errors)
            errors.extend(row_errors)
    if not errors:
        return {"tested": False, "reason": "no numeric rows"}
    errors.sort()
    return {"tested": True, "relationship": "spectrum = sample_raw / wr_raw",
            "rows_tested": rows_tested, "wavelengths": len(common), "points": points,
            "median_absolute_error": errors[len(errors) // 2],
            "maximum_absolute_error": errors[-1],
            "exact_within_1e-7_fraction": sum(e <= 1e-7 for e in errors) / len(errors)}
