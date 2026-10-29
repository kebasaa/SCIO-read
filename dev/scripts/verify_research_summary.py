"""Offline checks of the October 2026 outside summary; no device/network access.

Uses Git objects at the cited commit, not mutable current corpus files. This
reproduces corpus and complete-stream claims, not the unavailable layout sweep.
"""
import argparse
import hashlib
import json
import struct
import subprocess
import zlib
from collections import Counter
from pathlib import Path

import _bootstrap  # noqa: F401
import numpy as np
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from scio import session, store
from scio_offline import decode, research as r
from scio_offline.repeatability import plaintext_repeatability, verify_repeatability
from ingest_fw151_captures import parse_captures
from probe_stale_buffer import replay

REVISION = "135d8915388ae64f9c6ba90bb7fdd753d21323f7"
ROLES = ("sample", "sample_dark", "sample_white", "sample_white_dark")


def git_documents():
    entries = []
    tree = subprocess.check_output(["git", "ls-tree", "-rz", REVISION, "02_processed_data"])
    for entry in tree.split(b"\0"):
        if not entry:
            continue
        meta, path = entry.split(b"\t", 1)
        if path.endswith(b".json"):
            entries.append((path.decode(), meta.split()[-1].decode()))
    raw = subprocess.check_output(["git", "cat-file", "--batch"],
                                  input="".join(oid + "\n" for _, oid in entries).encode())
    pos, docs = 0, []
    for path, oid in entries:
        end = raw.index(b"\n", pos)
        actual_oid, kind, size = raw[pos:end].split()
        size = int(size)
        content = raw[end + 1:end + 1 + size]
        digest = hashlib.sha1(b"blob " + str(size).encode() + b"\0" + content).hexdigest()
        if actual_oid.decode() != oid or kind != b"blob" or digest != oid:
            raise ValueError("Git blob verification failed")
        docs.append((path, oid, json.loads(content)))
        pos = end + size + 2
    return docs


def complete_stream(data, wbits):
    """Bound output, require EOF and full input consumption, including trailers."""
    d = zlib.decompressobj(wbits)
    try:
        output = d.decompress(data, 1024 * 1024)
    except zlib.error:
        return False
    return bool(output) and d.eof and not d.unused_data and not d.unconsumed_tail


def codec_check(blobs):
    hits = []
    for digest, blob in sorted(blobs.items()):
        for offset in (0, 8):
            for codec, wbits in (("zlib", 15), ("gzip", 31), ("raw_deflate", -15)):
                if complete_stream(blob[offset:], wbits):
                    hits.append({"sha256": digest, "offset": offset, "codec": codec})
    return {"distinct_blobs": len(blobs), "attempts": len(blobs) * 6, "hits": hits,
            "output_cap_bytes": 1024 * 1024}


def repeatability_counterexample():
    """A known correct AES key can fail an integer-repeatability detector."""
    rng = np.random.default_rng(151)
    base = (10000 + 3000 * np.sin(np.arange(400) / 50)).astype("<u2")
    signals = [(base.astype(int) + rng.integers(-2, 3, 400)).astype("<u2").tobytes()
               for _ in range(2)]
    packed = [zlib.compress(v) for v in signals]
    size = (max(map(len, packed)) + 15) // 16 * 16
    packed = [v.ljust(size, b"\0") for v in packed]
    key = bytes(range(16))  # synthetic fixture, not a candidate device secret
    blobs = []
    for i, plain in enumerate(packed):
        enc = Cipher(algorithms.AES(key), modes.ECB()).encryptor()
        blobs.append(struct.pack("<II", 0, i + 1) + enc.update(plain) + enc.finalize())
    recovered = [decode.decrypt(b[8:], key, mode="ECB") for b in blobs]
    assert recovered == packed
    assert [zlib.decompress(v) for v in recovered] == signals
    return {"synthetic_only": True, "exact_decrypt_and_decompress": True,
            "signal_repeatability": plaintext_repeatability(*signals),
            "correct_plaintext_repeatability": plaintext_repeatability(*recovered),
            "existing_detector_with_correct_key": verify_repeatability(blobs, key),
            "limit": "Counterexample to universal key rejection, not evidence SCiO uses this codec or cipher."}


def audit():
    docs = git_documents()
    counts, blobs, encoding_checks, pairs = Counter(), {}, 0, []
    for path, oid, doc in docs:
        if not isinstance(doc, dict) or not doc.get("scan"):
            continue
        truth = doc.get("spectrum")
        if not isinstance(truth, dict) or not truth.get("reflectance"):
            continue
        rec = doc["scan"]
        counts[rec["device"]["i2s_tag_config"]] += 1
        y, wl = np.asarray(truth["reflectance"]), np.asarray(truth["wavelength_nm"])
        if y.shape != (331,) or not np.isfinite(y).all() or not np.array_equal(wl, np.arange(740, 1071)):
            raise ValueError("unexpected target spectrum")
        scan, white = session.record_blobs(rec)
        fields = {**rec["raw"], **rec["white_reference"]["blobs"]}
        for role, raw in {**scan, **white}.items():
            entry = fields[role]
            if len(raw) != entry["size"] or store.unwrap_b64(entry["b64"]) != raw:
                raise ValueError("encoding or size mismatch")
            encoding_checks += 1
            if role in ROLES:
                blobs[r.sha(raw)] = raw
        pairs.append({"path": path, "git_blob": oid})
    captures = parse_captures()
    contributed = {r.sha(b): b for s in captures["scans"] for b in s["frames"].values()}
    local = replay(r.DEV / "analysis_output/stale_buffer_20261028/rounds.json")
    return {"schema": "scio-summary-verification/1", "revision": REVISION,
            "git_json_files_verified": len(docs), "paired_records": len(pairs),
            "paired_groups": dict(counts), "target_axis": "331 points, 740..1070 nm",
            "blob_encoding_checks": encoding_checks, "pairs": pairs,
            "historical_complete_stream_check": codec_check(blobs),
            "fw151_complete_stream_check": codec_check(contributed),
            "fw151_scan_count": len(captures["scans"]),
            "fw151_word0_all_zero": captures["word0_all_zero"],
            "fw151_word1_unique": captures["word1_unique"],
            "local_battery_tail": local["battery_tail"],
            "local_missing_replies": local["missing_reply_contexts"],
            "repeatability_counterexample": repeatability_counterexample(),
            "not_reproduced": ["225680-layout sweep, its splits and RMSEs: original scripts absent",
                               "outside USB/Bluetooth/API traces and 44/44 result: raw evidence absent",
                               "any decryption or firmware recovery"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = audit()
    r.write_new(args.output, result)
    print(json.dumps({k: v for k, v in result.items() if k not in ("pairs",)}, indent=2))


if __name__ == "__main__":
    main()
