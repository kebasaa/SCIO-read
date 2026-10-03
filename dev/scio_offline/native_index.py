"""Index annotated AOT dumps without exporting arbitrary app constants."""
import hashlib
import re
from pathlib import Path

HEADER = re.compile(r"\*\* addr: (0x[0-9a-f]+), size: (0x[0-9a-f]+)")
POOL = re.compile(r"\[pp\+(0x[0-9a-f]+)\]")
CALL = re.compile(r"\bbl\s+#(0x[0-9a-f]+)")
LABELS = (
    "sample", "sample_dark", "sample_gradient", "white", "white_dark",
    "white_gradient", "sample_white", "sample_white_dark", "sample_white_gradient",
    "reflectance", "wavelengths", "i2s_tag_config", "device_id", "scio_edition",
    "deadPixelsIndices", "nPixelsPerBin", "compression_version",
    "firmware", "calibration", "i2s", "bins", "centers",
)


def functions(text):
    """Yield function metadata and lines; callers must not publish raw lines."""
    current = None
    for line_number, line in enumerate(text.splitlines(), 1):
        match = HEADER.search(line)
        if match:
            if current is not None:
                yield current
            current = {"address": match[1], "size": int(match[2], 16),
                       "line": line_number, "lines": []}
        if current is not None:
            current["lines"].append(line)
    if current is not None:
        yield current


def index_dump(root):
    root = Path(root)
    labels = {}
    for line in (root / "pp.txt").read_text(encoding="utf-8").splitlines():
        match = POOL.search(line)
        if match:
            for label in LABELS:
                if line.endswith('String: "' + label + '"'):
                    labels[match[1]] = label
    files, rows = [], []
    for path in sorted((root / "asm").rglob("*")):
        if not path.is_file():
            continue
        raw = path.read_bytes()
        relative = path.relative_to(root).as_posix()
        files.append({"path": relative, "sha256": hashlib.sha256(raw).hexdigest()})
        for fn in functions(raw.decode("utf-8")):
            text = "\n".join(fn.pop("lines"))
            refs = sorted(set(POOL.findall(text)) & labels.keys())
            rows.append({**fn, "file": relative, "pool_refs": refs,
                         "calls": sorted(set(CALL.findall(text)))})
    return {"schema": 1, "files": files, "functions": rows, "labels": labels,
            "limits": "Only direct BL calls and allowlisted exact object-pool labels. No dynamic-call resolution or proof of codec behavior."}
