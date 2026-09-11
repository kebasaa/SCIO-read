"""Is the blob body compressed rather than encrypted?

Consumer Physics calls the i2s tag ``compression_version`` - in the un-obfuscated
2017 build the parameter carrying it is literally named ``i2sTag`` - and ships
error strings ``MixedI2SCompression``, ``UnsupportedCompressionData`` and
``UnsupportedCompressionConversion``. You cannot convert between encryptions; you
can re-bin between binning tables. That vocabulary, plus a gradient blob whose
length changes with the generation (1656 B on ``-e``, 1416 B on ``-o``), is the
reason to take compression seriously.

Prior work tried exactly three decompressors (``zlib``, ``bz2``, ``lzma``) on the
raw body, caught the exception, and recorded zero hits. That is a much weaker test
than it looks:

* it required the *whole* body to decompress, so a stream with a prefix, a wrapper
  or a trailer fails even if the middle is a valid deflate stream;
* it never tried **raw** DEFLATE (no zlib header), which is what an embedded coder
  would emit;
* it never tried any **offset**, and never a **bit** offset - a bit-packed stream
  does not have to start on a byte boundary;
* it treated "threw an exception" as the only failure, discarding the partial
  output a truncated-but-real stream would still produce.

This module fixes all four.

**What a negative here does and does not mean.** It rules out *known* codecs at
any alignment. It cannot rule out a proprietary coder: a range/arithmetic coder
emits a headerless stream that is statistically indistinguishable from random, so
no sweep over standard formats would ever find it. A hit would be decisive; a miss
narrows the space and leaves both "a codec we did not guess" and "encryption"
alive. See ``dev/README.md`` for why the second can never be closed from this side
of the wire.
"""

from __future__ import annotations

import bz2
import json
import lzma
import zlib
from pathlib import Path

import numpy as np

from scio import session, store

from . import decode

try:                                    # optional, present in this environment
    import brotli
except ImportError:                     # pragma: no cover
    brotli = None

#: A decoded scan should be somewhere between the 331 output bands and the ~1200
#: values a 1792-byte body could hold. Far outside that and it is not pixel data.
MIN_VALUES, MAX_VALUES = 300, 4096
BYTE_OFFSETS = tuple(range(0, 33))
BIT_OFFSETS = tuple(range(0, 8))


# --------------------------------------------------------------------- helpers
def shift_bits(data: bytes, k: int) -> bytes:
    """Reinterpret *data* as a bit stream starting *k* bits in."""
    if k == 0:
        return data
    n = int.from_bytes(data, "big")
    n <<= k                              # drop the leading k bits
    n &= (1 << (len(data) * 8)) - 1
    return n.to_bytes(len(data), "big")


def _partial(decompressor, data: bytes) -> bytes:
    """Whatever a decompressor yields before it fails.

    This is the point of the module: a truncated or wrapped real stream still
    emits plaintext before erroring, and that partial output is the signal the
    previous all-or-nothing test threw away.
    """
    try:
        out = decompressor.decompress(data)
    except Exception:
        out = getattr(decompressor, "_partial", b"")
    return out or b""


def _raw_deflate(data: bytes) -> bytes:
    return _partial(zlib.decompressobj(-15), data)      # no zlib header


def _zlib(data: bytes) -> bytes:
    return _partial(zlib.decompressobj(), data)


def _gzip(data: bytes) -> bytes:
    return _partial(zlib.decompressobj(16 + zlib.MAX_WBITS), data)


def _bz2(data: bytes) -> bytes:
    return _partial(bz2.BZ2Decompressor(), data)


def _lzma_auto(data: bytes) -> bytes:
    return _partial(lzma.LZMADecompressor(format=lzma.FORMAT_AUTO), data)


def _lzma_raw(data: bytes) -> bytes:
    filters = [{"id": lzma.FILTER_LZMA1, "preset": 6}]
    try:
        return _partial(lzma.LZMADecompressor(format=lzma.FORMAT_RAW, filters=filters), data)
    except Exception:
        return b""


def _brotli(data: bytes) -> bytes:
    if brotli is None:
        return b""
    try:
        return brotli.decompress(data)
    except Exception:
        return b""


def _rle8(data: bytes) -> bytes:
    """(count, value) pairs - the cheapest plausible embedded scheme."""
    out = bytearray()
    for i in range(0, len(data) - 1, 2):
        out.extend(bytes([data[i + 1]]) * data[i])
        if len(out) > 1 << 16:
            break
    return bytes(out)


def _delta_u16(data: bytes) -> bytes:
    """Cumulative sum of int16 deltas - a standard spectrometer packing."""
    if len(data) < 4:
        return b""
    d = np.frombuffer(data[: len(data) // 2 * 2], dtype="<i2").astype(np.int64)
    return np.cumsum(d).astype("<i8").tobytes()


CODECS = {
    "raw_deflate": _raw_deflate,
    "zlib": _zlib,
    "gzip": _gzip,
    "bz2": _bz2,
    "lzma_auto": _lzma_auto,
    "lzma_raw": _lzma_raw,
    "brotli": _brotli,
    "rle8": _rle8,
    "delta_u16": _delta_u16,
}


# --------------------------------------------------------------------- scoring
def score_output(out: bytes) -> dict:
    """Is this plausibly a decoded scan, or just bytes?

    Two independent requirements, because either alone is easy to satisfy by
    accident: the length must fit a spectrum-shaped array, and the values must
    look like a physical measurement under the project's existing oracle.
    """
    if not out:
        return {"ok": False, "reason": "no output", "n_bytes": 0}
    best = decode.plaintext_score(out)
    n16 = len(out) // 2
    plausible_len = MIN_VALUES <= n16 <= MAX_VALUES
    return {
        "ok": bool(plausible_len and best.get("score", 0) >= 0.5),
        "n_bytes": len(out),
        "n_u16": n16,
        "plausible_length": plausible_len,
        "score": best.get("score"),
        "view": best.get("view"),
        "smooth": best.get("smooth"),
        "entropy": best.get("entropy"),
    }


def sweep_body(body: bytes, *, codecs=None, byte_offsets=BYTE_OFFSETS,
               bit_offsets=BIT_OFFSETS) -> list[dict]:
    """Every codec × byte offset × bit offset against one body.

    Returns only candidates that produced output at all; a run that yields
    nothing anywhere is itself the result.
    """
    codecs = codecs or CODECS
    hits = []
    for bit in bit_offsets:
        shifted = shift_bits(body, bit) if bit else body
        for off in byte_offsets:
            if off >= len(shifted):
                continue
            chunk = shifted[off:]
            for name, fn in codecs.items():
                try:
                    out = fn(chunk)
                except Exception:
                    continue
                if not out:
                    continue
                sc = score_output(out)
                hits.append({"codec": name, "byte_offset": off, "bit_offset": bit,
                             **sc})
    return hits


def screen_codecs(codecs=None, *, n_random: int = 32, size: int = 1792,
                  max_false_positive_rate: float = 0.02, seed: int = 0) -> dict:
    """Disqualify any codec that "finds" structure in random bytes.

    Not every transform can be scored by a smoothness oracle. ``delta_u16``, for
    instance, is a cumulative sum - and the cumsum of *any* input is a random
    walk, which has small consecutive deltas relative to its range and therefore
    scores ~0.96 on pure noise. Including it would guarantee a false positive on
    the real corpus.

    That is the same failure the project already hit twice (random bytes read as
    float32; sliding windows over firmware). Rather than blacklist by hand and
    hope the next addition is safe, every codec is measured against random input
    here and excluded automatically if it fires. A codec that cannot distinguish
    a scan from noise cannot contribute evidence either way.
    """
    codecs = codecs or CODECS
    rng = np.random.default_rng(seed)
    verdicts = {}
    for name, fn in codecs.items():
        fired = 0
        for _ in range(n_random):
            noise = bytes(rng.integers(0, 256, size, dtype=np.uint8))
            try:
                out = fn(noise)
            except Exception:
                out = b""
            if score_output(out)["ok"]:
                fired += 1
        rate = fired / n_random
        verdicts[name] = {
            "false_positive_rate": rate,
            "usable": bool(rate <= max_false_positive_rate),
        }
    return verdicts


def usable_codecs(screen: dict, codecs=None) -> dict:
    codecs = codecs or CODECS
    return {k: v for k, v in codecs.items() if screen.get(k, {}).get("usable")}


def corroborate(candidate: dict, bodies: list[bytes], *, min_bodies: int = 4) -> dict:
    """Do the same parameters work on other, independent bodies?

    The project has produced two false positives by taking a best-of-many-trials
    maximum at face value. This sweep is ~2,300 trials per body, so a single hit
    means nothing: the same (codec, byte offset, bit offset) must produce
    plausible output on at least *min_bodies* unrelated blobs, and the reported
    score is the **minimum** across them - one fluke collapses it.
    """
    fn = CODECS[candidate["codec"]]
    scores, oks = [], 0
    for body in bodies[: max(min_bodies, 8)]:
        shifted = shift_bits(body, candidate["bit_offset"]) if candidate["bit_offset"] else body
        try:
            out = fn(shifted[candidate["byte_offset"]:])
        except Exception:
            out = b""
        sc = score_output(out)
        scores.append(sc.get("score") or 0.0)
        oks += bool(sc["ok"])
    return {
        "bodies_tested": len(scores),
        "bodies_ok": oks,
        "min_score": float(min(scores)) if scores else 0.0,
        "corroborated": bool(oks >= min_bodies),
    }


# --------------------------------------------------------------------- driver
def run(limit_bodies: int | None = None, scans_dir=None) -> dict:
    """Sweep the corpus and report. Negative results are the expected outcome."""
    scans_dir = Path(scans_dir or store.SCANS_DIR)
    bodies, labels = [], []
    seen = set()
    for p in sorted(scans_dir.glob("*.json")):
        rec = session.load_record(p)
        scan_b, white_b = session.record_blobs(rec)
        for key, blob in {**scan_b, **white_b}.items():
            body = blob[8:]
            h = hash(body)
            if h in seen:                 # 3 white references are copied into 97 records
                continue
            seen.add(h)
            bodies.append(body)
            labels.append(f"{p.stem}:{key}")
    if limit_bodies:
        bodies, labels = bodies[:limit_bodies], labels[:limit_bodies]

    # Calibrate before measuring: a codec that scores well on noise cannot tell
    # us anything about the corpus, so it is excluded and reported, not silently
    # allowed to produce the "hit" this whole exercise is trying to avoid.
    screen = screen_codecs()
    live = usable_codecs(screen)

    all_hits, produced_output = [], 0
    for body, label in zip(bodies, labels):
        hits = sweep_body(body, codecs=live)
        produced_output += bool(hits)
        for h in hits:
            if h["ok"]:
                h["body"] = label
                all_hits.append(h)

    corroborated = []
    for cand in all_hits:
        c = corroborate(cand, bodies)
        if c["corroborated"]:
            corroborated.append({**cand, **c})

    trials = len(bodies) * len(BIT_OFFSETS) * len(BYTE_OFFSETS) * len(live)
    return {
        "schema": "scio-compression-sweep/1",
        "ran_at": store.now_iso(),
        "unique_bodies": len(bodies),
        "codec_screen": screen,
        "codecs_used": sorted(live),
        "codecs_excluded": sorted(set(CODECS) - set(live)),
        "byte_offsets": [min(BYTE_OFFSETS), max(BYTE_OFFSETS)],
        "bit_offsets": [min(BIT_OFFSETS), max(BIT_OFFSETS)],
        "total_trials": trials,
        "bodies_producing_any_output": produced_output,
        "scored_hits": len(all_hits),
        "corroborated_hits": corroborated,
        "verdict": ("compression_supported" if corroborated else "compression_not_demonstrated"),
        "encryption_hypothesis": "not_excluded",
        "encryption_reason": (
            "No software test can exclude encryption: the device could encrypt and the "
            "server decrypt, and the Android client is a verified byte-for-byte pass-through "
            "that would look identical either way."),
        "limits": (
            "Rules out known codecs at any byte/bit alignment. A proprietary range or "
            "arithmetic coder emits a headerless stream indistinguishable from random and "
            "would not be found by any sweep over standard formats."),
    }


def write_report(report: dict, path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=1), encoding="utf-8")
    return path
