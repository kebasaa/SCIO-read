"""Offline, bounded AES tests of the public sample UUID and all-zero key theory.

Run with --output dev/analysis_output/<new-directory>. Never opens a device or
network connection. No claim that AES, these IVs, or these codecs describe SCiO.
"""
import argparse
import hashlib
import uuid
import zlib
from collections import Counter
from pathlib import Path

import _bootstrap  # noqa: F401
import numpy as np
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from scio import session
from scio_offline import decode, research as r
from scio_offline.repeatability import verify_repeatability
from verify_research_summary import git_documents, REVISION
from ingest_fw151_captures import parse_captures
from probe_aptina_decrypt import role_blobs
from ingest_fw138_batches import parse_all

PUBLIC_UUID = "4b5ac28b-28f9-4695-b784-b7665dfe3763"
CODECS = (("zlib", 15), ("gzip", 31), ("raw_deflate", -15))
CAP = 1024 * 1024


def candidates():
    """Explicit candidates, deduplicated by bytes; no arbitrary password search."""
    values = {}
    for size in (16, 24, 32):
        values[f"binary_zero_{size}"] = bytes(size)
        values[f"ascii_zero_{size}"] = b"0" * size
    for label, value in (("sample_uuid", PUBLIC_UUID), ("zero_uuid", str(uuid.UUID(int=0)))):
        u = uuid.UUID(value)
        representations = {"binary": u.bytes, "guid_le": u.bytes_le,
                           "text": str(u).encode(), "hex_text": u.hex.encode()}
        for rep, raw in representations.items():
            if len(raw) in (16, 24, 32):
                values[f"{label}.{rep}.direct"] = raw
            values[f"{label}.{rep}.md5"] = hashlib.md5(raw).digest()
            values[f"{label}.{rep}.sha256"] = hashlib.sha256(raw).digest()
        values[f"{label}.binary.repeat32"] = u.bytes * 2
    # Literal six-character suggestion is not itself an AES key. Test named KDFs.
    values["six_ascii_zeros.md5"] = hashlib.md5(b"000000").digest()
    values["six_ascii_zeros.sha256"] = hashlib.sha256(b"000000").digest()
    unique = {}
    for label, key in values.items():
        unique.setdefault(key, []).append(label)
    return unique


def configurations():
    for offset in (0, 8):
        yield offset, "ECB", "zero"
        for mode in ("CBC", "CTR", "CFB", "OFB"):
            for iv in decode.IV_SCHEMES:
                yield offset, mode, iv


def decrypt_candidate(blob, key, offset, mode, iv):
    return decode.decrypt(blob[offset:], key, mode=mode, iv=iv, header=blob[:8])


def unpack(data, wbits):
    """Require complete bounded stream and only explicit zero/PKCS7 padding."""
    decoder = zlib.decompressobj(wbits)
    try:
        plain = decoder.decompress(data, CAP)
    except zlib.error:
        return None
    if not decoder.eof or decoder.unconsumed_tail or len(plain) < 64:
        return None
    tail = decoder.unused_data
    padding = "none"
    if tail:
        if tail == bytes(len(tail)):
            padding = "zero"
        elif len(tail) <= 16 and tail == bytes([len(tail)]) * len(tail):
            padding = "pkcs7"
        else:
            return None
    return {"output_bytes": len(plain), "output_sha256": r.sha(plain), "padding": padding}


def recognize(plain):
    hits = []
    for offset in (0, 8):
        for name, wbits in CODECS:
            result = unpack(plain[offset:], wbits)
            if result:
                hits.append({"codec": name, "plaintext_offset": offset, **result})
    return hits


def load_blobs():
    blobs, provenance = {}, {}
    for path, oid, doc in git_documents():
        if not isinstance(doc, dict) or not doc.get("scan") or not doc.get("spectrum", {}).get("reflectance"):
            continue
        scan, white = session.record_blobs(doc["scan"])
        tag = doc["scan"]["device"]["i2s_tag_config"]
        for role, data in {**scan, **white}.items():
            digest = r.sha(data)
            blobs[digest] = data
            provenance.setdefault(digest, []).append({"path": path, "git_blob": oid, "group": tag, "role": role})
    captures = parse_captures()
    for index, scan in enumerate(captures["scans"]):
        for role, data in scan["frames"].items():
            digest = r.sha(data)
            blobs[digest] = data
            provenance.setdefault(digest, []).append({"group": "contributor_fw151_unverified_identity", "scan": index, "role": role})
    return blobs, provenance


def positive_controls():
    """End-to-end controls where IV construction has no circular dependency."""
    original = bytes(range(256)) * 4
    packed = zlib.compress(original)
    packed += bytes([16 - len(packed) % 16]) * (16 - len(packed) % 16)
    header = b"SCIOtest"
    checked = 0
    for key in (bytes(16), bytes(24), bytes(32), uuid.UUID(PUBLIC_UUID).bytes):
        for offset, mode, scheme in configurations():
            if offset == 0 and scheme.startswith(("header8", "zero8")):
                continue
            embedded = bytes(range(16))
            iv = decode.make_iv(scheme, header, embedded)
            cipher_mode = modes.ECB() if mode == "ECB" else getattr(modes, mode)(iv)
            enc = Cipher(algorithms.AES(key), cipher_mode).encryptor()
            encrypted = enc.update(packed) + enc.finalize()
            if scheme == "first_block":
                encrypted = embedded + encrypted
            blob = (header if offset else b"") + encrypted
            plain = decrypt_candidate(blob, key, offset, mode, scheme)
            assert plain == packed
            assert any(h["output_sha256"] == r.sha(original) for h in recognize(plain))
            checked += 1
    return {"configurations_recovered": checked, "keys": ["zero128", "zero192", "zero256", "public_uuid128"],
            "note": "All modes/key sizes/IV schemes covered. Offset-zero header-derived cases lack end-to-end controls because IV would depend on ciphertext prefix."}


def run(output):
    output = output.resolve()
    if not output.is_relative_to(r.DEV) or output.exists():
        raise ValueError("choose a new output directory beneath dev")
    keys = candidates()
    controls = positive_controls()
    blobs, provenance = load_blobs()
    r.write_new(output / "plan.json", {"schema": "scio-app-zero-key-plan/1", "revision": REVISION,
        "keys": [{"labels": labels, "bytes": len(key), "sha256": r.sha(key)} for key, labels in keys.items()],
        "configurations": list(configurations()), "codec_plaintext_offsets": [0, 8],
        "codecs": [x[0] for x in CODECS], "min_decoded_bytes": 64, "max_decoded_bytes": CAP,
        "blob_manifest": [{"sha256": digest, "bytes": len(blobs[digest]), "sources": provenance[digest]} for digest in sorted(blobs)]})
    counts, hits = Counter(), []
    for digest, blob in sorted(blobs.items()):
        for offset in (0, 8):
            for hit in recognize(blob[offset:]):
                hits.append({"blob": digest, "transform": "identity", "ciphertext_offset": offset, **hit})
        for key, labels in keys.items():
            for offset, mode, iv in configurations():
                if mode in ("CBC", "ECB") and (len(blob) - offset) % 16:
                    counts["unaligned_block_configurations_skipped"] += 1
                    continue
                plain = decrypt_candidate(blob, key, offset, mode, iv)
                counts["decryptions"] += 1
                counts["codec_checks"] += 6
                for hit in recognize(plain):
                    hits.append({"blob": digest, "key_labels": labels, "ciphertext_offset": offset,
                                 "mode": mode, "iv": iv, **hit})
    print("Codec search:", dict(counts), "hits", len(hits), flush=True)
    r.write_new(output / "codec_results.json", {"positive_controls": controls, "counts": dict(counts), "hits": hits,
        "distinct_blobs": len(blobs), "unique_keys": len(keys),
        "interpretation": "Codec hits are provisional, not spectrum recovery. No hit does not reject other codecs, IVs or transforms."})
    batches = parse_all()
    repeat = {}
    rng = np.random.default_rng(20261029)
    random_keys = [rng.bytes(size) for size in (16, 24, 32) for _ in range(4)]
    for target in ("cap", "wood"):
        for role in ("sample", "dark", "gradient"):
            sample = role_blobs(batches, target, role, 8)
            if len(sample) < 8:
                raise ValueError("missing repeatability captures")
            rows = [{"labels": labels, **verify_repeatability(sample, key)} for key, labels in keys.items()]
            random_scores = [verify_repeatability(sample, key)["repeatability"] for key in random_keys]
            repeat[f"fw138/{target}/{role}"] = {"blob_sha256": [r.sha(b) for b in sample],
                "candidates": rows, "random_key_scores": random_scores,
                "screen_hits_at_0_5": [row for row in rows if row["repeatability"] >= 0.5]}
            print("Repeatability", target, role, "best", max(row["repeatability"] for row in rows), flush=True)
    r.write_new(output / "repeatability.json", {"groups": repeat,
        "limits": "Eight fw138 same-target captures per group; integer correlation screen with adaptive expansion, not a key proof. Compression can defeat this detector. No fitted spectrum decoder."})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    run(parser.parse_args().output)
