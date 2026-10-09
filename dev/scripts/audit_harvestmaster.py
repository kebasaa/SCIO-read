"""Static triage of third-party SCiO-integrating software (HarvestMaster / Mirus first).

Walks an already-extracted tree (nothing is installed or executed) and records, per file:
size, SHA-256, a coarse kind (.NET assembly / native PE / zip / other), a broad vocabulary
hit list searched in both ASCII and UTF-16LE (.NET string literals are UTF-16), and any
match against the known SCiO firmware / calibration-table sizes and firmware checksums.

The vocabulary is deliberately broad: an integrator may never say "SCiO" but name the
vendor (Consumer Physics, scionir), the band (NIR, spectro), or the payload fields
(sample_dark, i2s, compression_version). Hits are leads only, never evidence of a decoder.

Stdlib only, so it runs with an isolated interpreter (`python -I`) on untrusted extracts:

    python -I dev/scripts/audit_harvestmaster.py ROOT [ROOT ...] --output dev/analysis_output/<new-run>/inventory.json
"""
import argparse
import hashlib
import json
import re
import struct
import sys
from pathlib import Path

# Lower-case terms; matched case-insensitively. Grouped so a report reads by theme.
VOCAB = {
    "vendor": ["scio", "consumerphysics", "consumer physics", "consumer_physics", "scionir",
               "consumer-physics", "cpscan", "cp_scan", "harvestmaster nir"],
    "spectral": ["spectro", "spectrum", "spectra", "reflectance", "wavelength", "nir sensor",
                 "nir_", "absorbance", "pixel", "receptor"],
    "payload": ["sample_dark", "sample_white", "sample_gradient", "white_dark", "i2s",
                "compression_version", "20150812", "bad_sample_signature", "spectro-scan",
                "device_id", "dsp_id", "aptina"],
    "firmware": ["dsp_op", "dsp_boot", "dsp_dec", "npixelsperbin", "deadpixels", "bf512",
                 "blackfin", "cc2540", ".ldr", "firmware"],
    "crypto": ["aes", "rijndael", "aesmanaged", "aesgcm", "cryptostream", "bouncycastle",
               "hmac", "rsa", "decrypt", "encrypt", "privatekey", "secretkey", "licens"],
    "transport": ["localhost:8080", "/v1/", "is_connected", "export_scans", "self_test",
                  "last_data_sync", "serialport", "com port"],
}

# Known SCiO sizes (README §5, HANDOVER "Size arithmetic", foreign_fw138 FINDINGS §3).
KNOWN_SIZES = {
    7284: "dsp_boot (v17)", 14600: "dsp_dec (v12)", 32628: "dsp_op fw-147", 32212: "dsp_op fw-138",
    96: "centers table", 140: "bins table", 1166: "nPixelsPerBin fw-147",
    1792: "sample/dark body", 1800: "sample/dark blob", 1648: "gradient body -e",
    1656: "gradient blob -e", 1408: "gradient body -o/bare", 1416: "gradient blob -o/bare",
}
KNOWN_CHECKSUMS = {4151168: "dsp_op fw-147 checksum", 4101455: "dsp_op fw-138 checksum"}


def kind(data):
    """Coarse file kind from magic bytes; '.net' when a PE has a CLI header."""
    if data[:2] == b"MZ" and len(data) > 0x40:
        pe = struct.unpack_from("<I", data, 0x3C)[0]
        if data[pe:pe + 4] == b"PE\0\0":
            magic = struct.unpack_from("<H", data, pe + 24)[0]
            dd = pe + 24 + (96 if magic == 0x10B else 112)  # data directories
            if dd + 15 * 8 + 8 <= len(data):
                cli_rva = struct.unpack_from("<I", data, dd + 14 * 8)[0]
                return ".net" if cli_rva else "pe"
        return "pe"
    for magic, name in ((b"PK\x03\x04", "zip"), (b"MSCF", "cab"),
                        (b"\xd0\xcf\x11\xe0", "ole/msi"), (b"\x7fELF", "elf")):
        if data.startswith(magic):
            return name
    return "other"


def vocab_hits(data):
    """{group: {term: count}} over ASCII and UTF-16LE renderings, case-insensitive."""
    low = data.lower()
    out = {}
    for group, terms in VOCAB.items():
        found = {}
        for t in terms:
            n = low.count(t.encode()) + low.count(t.encode("utf-16-le"))
            if n:
                found[t] = n
        if found:
            out[group] = found
    return out


def context(data, term, width=60, limit=5):
    """Short printable snippets around the first `limit` ASCII/UTF-16 hits of `term`."""
    snippets = []
    low = data.lower()
    for enc in ("ascii", "utf-16-le"):
        needle = term.encode(enc)
        for m in re.finditer(re.escape(needle), low):
            raw = data[max(0, m.start() - width * (2 if enc != "ascii" else 1)):
                       m.end() + width * (2 if enc != "ascii" else 1)]
            text = raw.decode(enc, "replace") if enc == "ascii" else raw.decode(enc, "replace")
            snippets.append(re.sub(r"[^\x20-\x7e]", ".", text))
            if len(snippets) >= limit:
                return snippets
    return snippets


def checksum_hits(data):
    """Offsets where a known firmware checksum appears as a little-endian u32."""
    hits = {}
    for value, label in KNOWN_CHECKSUMS.items():
        needle = struct.pack("<I", value)
        offs = [m.start() for m in re.finditer(re.escape(needle), data)][:10]
        if offs:
            hits[label] = offs
    return hits


def audit(roots, snippet_terms=()):
    rows = []
    for root in roots:
        for path in sorted(p for p in Path(root).rglob("*") if p.is_file()):
            data = path.read_bytes()
            row = {
                "path": str(path.relative_to(root)).replace("\\", "/"),
                "root": Path(root).name,
                "size": len(data),
                "sha256": hashlib.sha256(data).hexdigest(),
                "kind": kind(data),
                "vocab": vocab_hits(data),
            }
            if len(data) in KNOWN_SIZES:
                row["known_size"] = KNOWN_SIZES[len(data)]
            ck = checksum_hits(data)
            if ck:
                row["checksum_hits"] = ck
            snips = {t: context(data, t) for t in snippet_terms if t.encode() in data.lower()
                     or t.encode("utf-16-le") in data.lower()}
            if snips:
                row["snippets"] = snips
            rows.append(row)
    return rows


def summarise(rows):
    """Files ranked by vendor + payload + firmware vocabulary weight."""
    def score(r):
        v = r["vocab"]
        return (sum(v.get("vendor", {}).values()) * 3 + sum(v.get("payload", {}).values()) * 2
                + sum(v.get("firmware", {}).values()) + 50 * bool(r.get("checksum_hits")))
    ranked = sorted((r for r in rows if score(r)), key=score, reverse=True)
    return [{"root": r["root"], "path": r["path"], "kind": r["kind"], "score": score(r),
             "vocab": r["vocab"], **({"checksum_hits": r["checksum_hits"]}
                                     if "checksum_hits" in r else {})} for r in ranked]


def main():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("roots", nargs="+", type=Path)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--snippet", action="append", default=[],
                   help="term to capture context snippets for (repeatable)")
    p.add_argument("--top", type=int, default=40)
    a = p.parse_args()
    if a.output.exists():
        raise FileExistsError(a.output)
    rows = audit(a.roots, [s.lower() for s in a.snippet])
    ranked = summarise(rows)
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text(json.dumps({"schema": "harvestmaster-audit/1",
                                    "roots": [r.name for r in a.roots],
                                    "n_files": len(rows), "ranked": ranked, "files": rows},
                                   indent=1))
    for r in ranked[:a.top]:
        print(f"{r['score']:6d} {r['kind']:7s} {r['root']}/{r['path']}  "
              f"{json.dumps({k: sorted(v) for k, v in r['vocab'].items() if k != 'crypto'})}")
    sized = [r for r in rows if "known_size" in r and r["kind"] == "other"]
    for r in sized:
        print(f"size-match {r['known_size']}: {r['root']}/{r['path']}")
    print(f"{len(rows)} files, {len(ranked)} with vocabulary hits -> {a.output}", file=sys.stderr)


if __name__ == "__main__":
    main()
