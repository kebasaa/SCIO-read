"""Identifier-key hypotheses the earlier AES/TEA/XTEA searches could not have seen.

Gaps closed (see dev/HANDOVER.md, README section 3):
  * the BLE MAC and identifier *pairs* with TEA/XTEA (the old TEA run had neither);
  * the full 16-byte Aptina sensor id (0x01 [8:24]); only [16:24] was ever parsed;
  * the restored 30-char serial prefix;
  * ciphers other than AES/TEA/XTEA: ARC4, ChaCha20, TripleDES, Blowfish, Camellia.

Everything is a bounded, auditable hypothesis keyed on device *identity* only -
single fields and pairs, no brute force. A repeatable-plaintext score is a lead,
never a decoded spectrum; a hit needs the held-out spectral validation the
recovery harness already defines. Read-only: captures in, report out.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import numpy as np
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from . import decode, keyrecover
from .embedded_cipher_hypothesis import decrypt_body as tea_decrypt_body
from .repeatability import plaintext_repeatability
from .research import sha


def aptina_key_forms(device: dict) -> dict:
    """Raw-byte keys from the 16-byte Aptina id and its halves (never hashed here).

    ``aptinaId`` is the full value word-swapped as the 2023 app stored it; the live
    0x01 reply gives the two 8-byte halves. Only [16:24] was ever a candidate before.
    """
    out: dict[str, bytes] = {}
    sources = {}
    full = device.get("aptinaId") or device.get("aptina_full")
    if full:
        sources["aptina_full"] = full
    for half_name in ("aptina_upper", "aptina_field"):
        if device.get(half_name):
            sources[half_name] = device[half_name]
    for name, hexstr in sources.items():
        try:
            raw = bytes.fromhex(hexstr)
        except ValueError:
            continue
        forms = {"raw": raw, "rev": raw[::-1],
                 "wswap": b"".join(raw[i:i + 2][::-1] for i in range(0, len(raw) - 1, 2))}
        if len(raw) == 8:  # expand an 8-byte half to a 16-byte key two ways
            forms = {"zeropad16": raw + bytes(8), "repeat16": raw + raw, "rev_zeropad16": raw[::-1] + bytes(8)}
        for form, key in forms.items():
            if len(key) in (16, 24, 32):
                out[f"{name}.bytes.{form}"] = key
    return out


# ---- cipher adapters: body -> plaintext bytes, or None if inapplicable --------
def _block_modes(header: bytes, body: bytes, block: int):
    """(label, cipher-mode) pairs mirroring the AES run, at this cipher's block size."""
    yield "ECB", modes.ECB()
    ivs = {"zero": bytes(block), "header": (header * ((block // 8) + 1))[:block],
           "header_zero": (header[:block // 2] + bytes(block))[:block]}
    for name, iv in ivs.items():
        yield f"CBC-{name}", modes.CBC(iv)
        yield f"CFB-{name}", modes.CFB(iv)
        yield f"OFB-{name}", modes.OFB(iv)


def _run_block(alg, key, header, body):
    rows = []
    block = alg.block_size // 8
    usable = body[:len(body) - len(body) % block]
    if len(usable) < block * 2:
        return rows
    for label, mode in _block_modes(header, usable, block):
        try:
            d = Cipher(alg, mode).decryptor()
            rows.append((label, d.update(usable) + d.finalize()))
        except Exception:
            continue
    return rows


def decrypt_variants(cipher: str, key: bytes, header: bytes, body: bytes):
    """Yield (config_label, plaintext) for one cipher/key, or nothing if key size is wrong."""
    try:
        if cipher in ("TEA", "XTEA"):
            if len(key) != 16:
                return
            for endian in ("big", "little"):
                for mode in ("ECB", "CBC-zero"):
                    yield f"{endian}.{mode}", tea_decrypt_body(body, key, cipher, endian, mode)
        elif cipher == "ARC4":
            d = Cipher(algorithms.ARC4(key), None).decryptor()
            yield "stream", d.update(body)
        elif cipher == "ChaCha20":
            if len(key) != 32:
                return
            for name, nonce in (("zero", bytes(16)), ("header", (header * 2)[:16])):
                d = Cipher(algorithms.ChaCha20(key, nonce), None).decryptor()
                yield f"nonce_{name}", d.update(body)
        elif cipher == "TripleDES":
            if len(key) not in (16, 24):
                return
            for label, plain in _run_block(algorithms.TripleDES(key), key, header, body):
                yield label, plain
        elif cipher == "Blowfish":
            if not 4 <= len(key) <= 56:
                return
            for label, plain in _run_block(algorithms.Blowfish(key), key, header, body):
                yield label, plain
        elif cipher == "Camellia":
            if len(key) not in (16, 24, 32):
                return
            for label, plain in _run_block(algorithms.Camellia(key), key, header, body):
                yield label, plain
    except Exception:
        return


CIPHERS = ("TEA", "XTEA", "ARC4", "ChaCha20", "TripleDES", "Blowfish", "Camellia")


def _identity_device(records, extra_device=None) -> dict:
    device = {}
    for record in records:
        device.update({k: v for k, v in record.device.items() if v not in (None, "")})
    if extra_device:
        device.update({k: v for k, v in extra_device.items() if v})
    return device


def build_keys(device: dict) -> dict:
    """All identity-derived candidate keys, de-duplicated by raw key bytes."""
    by_key: dict[bytes, list] = {}
    for label, key in keyrecover.candidate_keys_from_device(device).items():
        by_key.setdefault(key, []).append(label)
    for label, key in aptina_key_forms(device).items():
        by_key.setdefault(key, []).append(label)
    return by_key


def search(records, *, ciphers=CIPHERS, max_scans=6, workers=8, hit_threshold=0.5,
           expansion_threshold=0.12, random_count=128, dry_run=False):
    """Screen identity keys across the gap ciphers; confirm leads on the other scans."""
    split = [decode.split_blob(r.blobs["sample"]) for r in records if "sample" in r.blobs][:max_scans]
    headers = [s.header for s in split]
    bodies = [s.body for s in split]
    device = _identity_device(records)
    by_key = build_keys(device)

    if dry_run:
        n = sum(sum(1 for _ in decrypt_variants(c, k, headers[0], bodies[0]))
                for c in ciphers for k in by_key)
        return {"unique_keys": len(by_key), "ciphers": list(ciphers),
                "configs_on_first_blob": n, "scans": len(bodies)}

    def evaluate(item):
        key, labels = item
        best = None
        for cipher in ciphers:
            for config, first_plain in decrypt_variants(cipher, key, headers[0], bodies[0]):
                pair = plaintext_repeatability(first_plain, _decrypt_at(cipher, key, headers[1], bodies[1], config))
                score = pair["score"]
                if score >= expansion_threshold and len(bodies) > 2:
                    rest = [plaintext_repeatability(first_plain,
                            _decrypt_at(cipher, key, headers[i], bodies[i], config))["score"]
                            for i in range(2, len(bodies))]
                    score = float(np.median([pair["score"], *rest]))
                row = {"labels": labels, "candidate_sha256": sha(key), "key_len": len(key),
                       "cipher": cipher, "config": config, "repeatability": score,
                       "initial_pair": pair["score"], "view": pair["view"], "offset": pair["offset"]}
                if best is None or row["repeatability"] > best["repeatability"]:
                    best = row
        return best

    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        rows = [r for r in pool.map(evaluate, by_key.items()) if r]

    null = _random_controls(ciphers, headers, bodies, random_count)
    rows.sort(key=lambda r: r["repeatability"], reverse=True)
    null_max = max(null) if null else 1.0
    hits = [r for r in rows if r["repeatability"] >= hit_threshold and r["repeatability"] > null_max]
    return {"schema": "scio-identifier-cipher-gap/1", "scans": len(bodies),
            "unique_keys": len(by_key), "ciphers": list(ciphers),
            "blob_sha256": [sha(b) for b in bodies],
            "key_manifest": [{"sha256": sha(k), "derivations": v} for k, v in by_key.items()],
            "random_controls": {"count": len(null), "best_scores": null, "max": null_max},
            "hit_threshold": hit_threshold, "hits": hits, "top_candidates": rows[:50],
            "validated_decoder": False,
            "limits": "A repeatability lead is not a decoded spectrum; confirm against held-out "
                      "server spectra before any claim. A miss excludes none of: encryption, "
                      "another key, or compressed plaintext.",
            "conclusion": "provisional repeatability hit" if hits else
                          "no identity-derived key produced repeatable plaintext across these ciphers"}


def _decrypt_at(cipher, key, header, body, config):
    for label, plain in decrypt_variants(cipher, key, header, body):
        if label == config:
            return plain
    return b""


def _random_controls(ciphers, headers, bodies, count):
    rng = np.random.default_rng(7319)
    out = []
    for i in range(count):
        key = rng.bytes((16, 24, 32)[i % 3])
        best = -1.0
        for cipher in ciphers:
            for config, plain in decrypt_variants(cipher, key, headers[0], bodies[0]):
                s = plaintext_repeatability(plain, _decrypt_at(cipher, key, headers[1], bodies[1], config))["score"]
                if np.isfinite(s):
                    best = max(best, s)
        out.append(best)
    return out
