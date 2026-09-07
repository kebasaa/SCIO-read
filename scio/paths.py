"""Portable path labels for reports and capture metadata.

Public artifacts must not disclose a contributor's home-directory layout.  Paths
inside this repository are recorded relative to its root; external paths retain
only their basename and an explicit marker.
"""

from __future__ import annotations

from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parent.parent


def portable_path(value: str | Path | None) -> str | None:
    """Return a stable, non-identifying representation of *value*."""
    if value is None:
        return None
    path = Path(value)
    try:
        resolved = path.resolve()
        return resolved.relative_to(REPOSITORY_ROOT).as_posix()
    except (OSError, ValueError):
        return f"<external>/{path.name}"
