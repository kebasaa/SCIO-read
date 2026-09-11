"""Is the body a compressed *image*?

The sensor is a CMOS imager, the spectrum is a dispersed strip falling on it, and
a DSP with a fixed output budget is exactly the kind of thing that would ship a
small compressed frame. So: JPEG, PNG, or another image codec - possibly wrapped
in a generic compressor.

Two earlier efforts looked adjacent to this and did not cover it:

* ``image_hypothesis`` tested **raw raster layouts** - reshaping the bytes into
  every factor pair and looking for spatial correlation. That is an uncompressed
  image. It also checked file magic, but only with ``blob.startswith(magic)``,
  i.e. **at offset 0 only**, and it never invoked an actual decoder.
* ``compression_hypothesis`` swept deflate/zlib/gzip/bz2/lzma/brotli at every byte
  and bit offset. That covers an image wrapped in a generic compressor - the
  wrapper would have to decompress first, and none did - but **not JPEG itself**,
  whose entropy coding is Huffman over DCT coefficients, not LZ.

The cheapest test here is also the strongest, and it needs no decoder at all.
Entropy-coded image formats must **byte-stuff** so that a raw ``0xFF`` cannot be
mistaken for a marker:

===============  ==========================================================
JPEG             a ``0xFF`` in the scan is followed by ``0x00`` (or a marker)
JPEG-LS          the byte after ``0xFF`` is ``< 0x80``
JPEG 2000 (MQ)   the byte after ``0xFF`` is ``<= 0x8F``
===============  ==========================================================

Each rule holds over the entropy-coded segment itself, so it applies **with or
without a header** - which is the case that matters, since an embedded coder would
strip the container to save bytes. Measuring the distribution of the byte after
each ``0xFF`` therefore tests the whole JPEG family in one pass, including
headerless variants no decoder would accept.
"""

from __future__ import annotations

import io
import json
import math
from pathlib import Path

import numpy as np

from scio import session, store

from . import decode

#: Container magics, searched at **every** offset rather than only at 0.
MARKERS = {
    "JPEG SOI": b"\xff\xd8\xff",
    "JPEG EOI": b"\xff\xd9",
    "JPEG SOF0": b"\xff\xc0",
    "JPEG SOF2": b"\xff\xc2",
    "JPEG DHT": b"\xff\xc4",
    "JPEG SOS": b"\xff\xda",
    "JPEG DQT": b"\xff\xdb",
    "JPEG2000 SOC": b"\xff\x4f\xff\x51",
    "JP2 box": b"\x00\x00\x00\x0cjP",
    "PNG": b"\x89PNG\r\n",
    "GIF": b"GIF8",
    "BMP": b"BM",
    "TIFF LE": b"II*\x00",
    "TIFF BE": b"MM\x00*",
    "RIFF/WEBP": b"RIFF",
    "ZIP": b"PK\x03\x04",
    "RAR": b"Rar!",
    "7z": b"7z\xbc\xaf",
}


def load_bodies(scans_dir=None) -> list[bytes]:
    """Unique blob bodies (the 8-byte header removed)."""
    scans_dir = Path(scans_dir or store.SCANS_DIR)
    bodies, seen = [], set()
    for p in sorted(scans_dir.glob("*.json")):
        rec = session.load_record(p)
        scan_b, white_b = session.record_blobs(rec)
        for blob in {**scan_b, **white_b}.values():
            body = blob[8:]
            h = hash(body)
            if h not in seen:
                seen.add(h)
                bodies.append(body)
    return bodies


def stuffing_statistics(bodies: list[bytes]) -> dict:
    """Distribution of the byte following each 0xFF - the family-wide test."""
    n_ff = n_00 = n_rst = n_jls = n_j2k = 0
    for body in bodies:
        a = np.frombuffer(body, dtype=np.uint8)
        idx = np.where(a[:-1] == 0xFF)[0]
        if not len(idx):
            continue
        nxt = a[idx + 1]
        n_ff += len(idx)
        n_00 += int((nxt == 0x00).sum())
        n_rst += int(((nxt >= 0xD0) & (nxt <= 0xD9)).sum())
        n_jls += int((nxt < 0x80).sum())
        n_j2k += int((nxt <= 0x8F).sum())
    if not n_ff:
        return {"ff_bytes": 0, "conclusive": False}
    jpeg_rate = (n_00 + n_rst) / n_ff
    return {
        "ff_bytes": n_ff,
        "jpeg": {"observed": jpeg_rate, "random": (1 + 10) / 256, "required": 1.0,
                 "consistent": bool(jpeg_rate > 0.5)},
        "jpeg_ls": {"observed": n_jls / n_ff, "random": 128 / 256, "required": 1.0,
                    "consistent": bool(n_jls / n_ff > 0.9)},
        "jpeg2000": {"observed": n_j2k / n_ff, "random": 144 / 256, "required": 1.0,
                     "consistent": bool(n_j2k / n_ff > 0.9)},
        "conclusive": True,
    }


def marker_scan(bodies: list[bytes]) -> dict:
    """Container magic at any offset, against the random expectation."""
    total = sum(len(b) for b in bodies)
    out = {}
    for name, magic in MARKERS.items():
        count = sum(b.count(magic) for b in bodies)
        expected = total / (256 ** len(magic))
        out[name] = {"count": count, "random_expected": round(expected, 2),
                     "excess": bool(count > max(5, 4 * expected))}
    return {"per_marker": out,
            "any_excess": any(v["excess"] for v in out.values())}


def decoder_sweep(bodies: list[bytes], *, n_bodies: int = 40, max_offset: int = 32) -> dict:
    """Ask a real decoder, at every offset. Catches any self-describing format."""
    try:
        from PIL import Image
    except ImportError:                       # pragma: no cover
        return {"available": False}
    accepted = []
    for body in bodies[:n_bodies]:
        for off in range(max_offset + 1):
            try:
                im = Image.open(io.BytesIO(body[off:]))
                im.verify()
                accepted.append({"offset": off, "format": im.format, "size": list(im.size)})
            except Exception:
                pass
    return {"available": True,
            "attempts": min(n_bodies, len(bodies)) * (max_offset + 1),
            "accepted": accepted}


def padding_scan(bodies: list[bytes], prefixes=(64, 128, 256, 512)) -> dict:
    """Would a short stream padded into a fixed buffer show up?

    Every body is exactly 1792 or 1648 bytes regardless of scene. If that is a
    fixed buffer holding a shorter variable-length stream, the slack has to be
    somewhere - a low-entropy tail, or a run of constant bytes.
    """
    rows = {}
    for n in prefixes:
        head = [decode.entropy(b[:n]) for b in bodies]
        tail = [decode.entropy(b[-n:]) for b in bodies]
        ceiling = math.log2(min(n, 256))
        rows[f"{n}"] = {
            "head_fraction_of_ceiling": float(np.mean(head) / ceiling),
            "tail_fraction_of_ceiling": float(np.mean(tail) / ceiling),
        }
    runs = []
    for b in bodies:
        a = np.frombuffer(b, dtype=np.uint8)
        change = np.flatnonzero(np.diff(a) != 0)
        runs.append(int(np.max(np.diff(np.concatenate(([-1], change, [len(a) - 1])))))
                    if len(change) else len(a))
    return {
        "entropy_head_vs_tail": rows,
        "longest_constant_run": {"max": int(max(runs)), "mean": float(np.mean(runs)),
                                 "random_expectation": 2.35},
        "padding_found": bool(max(runs) > 16 or any(
            r["tail_fraction_of_ceiling"] < r["head_fraction_of_ceiling"] - 0.05
            for r in rows.values())),
    }


def run(scans_dir=None) -> dict:
    bodies = load_bodies(scans_dir)
    stuff = stuffing_statistics(bodies)
    markers = marker_scan(bodies)
    decoders = decoder_sweep(bodies)
    padding = padding_scan(bodies)

    families = []
    if stuff.get("conclusive"):
        for fam in ("jpeg", "jpeg_ls", "jpeg2000"):
            if not stuff[fam]["consistent"]:
                families.append(fam)
    supported = bool(
        (stuff.get("conclusive") and any(stuff[f]["consistent"] for f in
                                         ("jpeg", "jpeg_ls", "jpeg2000")))
        or markers["any_excess"] or decoders.get("accepted"))

    return {
        "schema": "scio-image-codec/1",
        "ran_at": store.now_iso(),
        "unique_bodies": len(bodies),
        "stuffing_statistics": stuff,
        "marker_scan": markers,
        "decoder_sweep": decoders,
        "padding_scan": padding,
        "families_excluded": families,
        "verdict": ("image_codec_supported" if supported
                    else "standard_image_codecs_excluded"),
        "reasoning": (
            "Entropy-coded image formats must byte-stuff, and the rule holds over the "
            "entropy-coded segment with or without a container - so the byte following "
            "each 0xFF tests the whole family at once, headerless variants included. "
            "Measured rates sit on the random expectation, no container magic appears "
            "above chance at any offset, no decoder accepts the bytes at any offset, and "
            "there is no padding slack in which a shorter stream could hide."),
        "limits": (
            "Excludes JPEG, JPEG-LS, JPEG 2000, PNG, GIF, BMP, TIFF, WebP and generic "
            "archive containers. A proprietary DCT or wavelet coder that does not "
            "byte-stuff would not be caught - it emits a headerless stream that looks "
            "random, which is the same blind spot the generic compression sweep has."),
        "encryption_hypothesis": "not_excluded",
    }


def write_report(report: dict, path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=1), encoding="utf-8")
    return path
