"""Bounded tests of SCIO cryptographic-key hypotheses.

Strategy (no brute-forcing of key spaces):

1. **Triage** a DSP artifact to decide whether it is analysable plaintext or
   remains opaque. (delegated to
   :mod:`scio.firmware`.)
2. **Scan** the firmware for cipher signatures - AES S-box / inverse S-box,
   AES round constants, XTEA delta, RC4/ChaCha constants - and report where
   they are. Their presence supports a cipher hypothesis; absence is
   inconclusive because code may use generated tables or a different transform.
3. **Harvest candidate keys** from local firmware-like artifacts and derive a
   bounded, auditable set from observed serial/device/sensor/BLE/version fields.
4. **Verify** each candidate against real captured scans using the plaintext
   oracle in :mod:`scio.decode`. A hit remains provisional until the derived
   result matches held-out server spectra and physical references.

Neither encryption nor any identifier-based key derivation is presumed. A
smooth output is only a pre-screen; it is not a recovered key without exact
cross-scan and held-out spectral validation.
"""

from __future__ import annotations

import hashlib
import itertools
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

from . import decode, firmware
from .decode import MODES, IV_SCHEMES

# AES forward S-box (first 16 bytes) - enough to locate the full 256-byte table.
_AES_SBOX_HEAD = bytes.fromhex("637c777bf26b6fc53001672bfed7ab76")
_AES_SBOX_INV_HEAD = bytes.fromhex("52096ad53036a538bf40a39e81f3d7fb")
# AES key-schedule round constants (Rcon), as they often appear as a table.
_AES_RCON = bytes([0x01, 0x02, 0x04, 0x08, 0x10, 0x20, 0x40, 0x80, 0x1B, 0x36])
_XTEA_DELTA = (0x9E3779B9).to_bytes(4, "little")
_XTEA_DELTA_BE = (0x9E3779B9).to_bytes(4, "big")
_CHACHA = b"expand 32-byte k"

_SIGNATURES = {
    "AES_SBOX": _AES_SBOX_HEAD,
    "AES_INV_SBOX": _AES_SBOX_INV_HEAD,
    "AES_RCON": _AES_RCON,
    "XTEA_DELTA_LE": _XTEA_DELTA,
    "XTEA_DELTA_BE": _XTEA_DELTA_BE,
    "CHACHA_SIGMA": _CHACHA,
}


def find_signatures(data: bytes) -> dict:
    """Return ``{signature_name: [offsets]}`` for known cipher constants."""
    hits = {}
    for name, needle in _SIGNATURES.items():
        offs, start = [], 0
        while True:
            i = data.find(needle, start)
            if i < 0:
                break
            offs.append(i)
            start = i + 1
        if offs:
            hits[name] = offs
    return hits


def _kdf_forms(seed: bytes) -> dict:
    """Auditable common derivations; no password/key-space brute force."""
    out = {}
    if len(seed) in (16, 24, 32):
        out["raw"] = seed
    if len(seed) < 16:
        out["zeropad16"] = (seed + bytes(16))[:16]
        out["repeat16"] = (seed * (16 // max(1, len(seed)) + 1))[:16]
    out["md5"] = hashlib.md5(seed).digest()          # 16
    out["sha1_16"] = hashlib.sha1(seed).digest()[:16]
    out["sha1_20_pad24"] = hashlib.sha1(seed).digest() + bytes(4)
    out["sha256_16"] = hashlib.sha256(seed).digest()[:16]
    out["sha256_24"] = hashlib.sha256(seed).digest()[:24]
    out["sha256"] = hashlib.sha256(seed).digest()    # 32
    out["sha512_16"] = hashlib.sha512(seed).digest()[:16]
    out["sha512_24"] = hashlib.sha512(seed).digest()[:24]
    out["sha512_32"] = hashlib.sha512(seed).digest()[:32]
    return out


def candidate_keys_from_device(device: dict) -> dict:
    """Derive a bounded set from locally observed identifiers and versions.

    These are hypotheses only. Candidate names fully describe the input and
    derivation so negative results can be reproduced and de-duplicated.
    """
    cands = {}
    fields = {
        "aptina_field": device.get("aptina_field") or device.get("aptinaId"),
        "device_id": device.get("device_id"),
        "dsp_id": device.get("dsp_id") or device.get("deviceDspId"),
        "ble_id": device.get("ble_id") or device.get("deviceBleId"),
        "i2s": device.get("i2s_tag_config"),
        "serial": device.get("serial_number"),
        "serial_short": device.get("serial") or device.get("serialNumber"),
        "serial_fragment": device.get("device_serial_fragment"),
        "case_serial": device.get("case_serial"),
        "sensor_id": device.get("sensor_id") or device.get("sensorId"),
        "bluetooth_address": device.get("address") or device.get("bluetooth_address"),
        "device_name": device.get("device_name") or device.get("name"),
        "firmware_version": device.get("firmware_version"),
        "dsp_version": device.get("dsp_version"),
        "hardware_version": device.get("hardware_version"),
        "ble_fw_version": device.get("ble_fw_version"),
    }
    fields = {k: str(v).strip() for k, v in fields.items() if v is not None and str(v).strip()}

    # Single fields, preserving the observed text and two common normal forms.
    for label, value in fields.items():
        variants = {"ascii": value.encode(), "ascii_lower": value.lower().encode(),
                    "ascii_upper": value.upper().encode()}
        compact = value.replace(":", "").replace("-", "").replace(" ", "")
        if compact != value:
            variants["ascii_compact"] = compact.encode()
        try:
            hexbytes = bytes.fromhex(compact)
            variants["hex"] = hexbytes
            variants["hex_rev"] = hexbytes[::-1]
            variants["hex_wswap"] = b"".join(
                hexbytes[i:i + 2][::-1] for i in range(0, len(hexbytes) - 1, 2))
        except ValueError:
            pass
        for enc, seed in variants.items():
            for kdf, key in _kdf_forms(seed).items():
                if len(key) in (16, 24, 32):
                    cands[f"{label}.{enc}.{kdf}"] = key

    # Pairwise combinations only: enough to cover device+sensor/version
    # constructions without inventing an exponential key space.
    identity_order = [k for k in ("device_id", "aptina_field", "dsp_id", "ble_id",
                                   "bluetooth_address", "serial", "serial_short",
                                   "serial_fragment", "case_serial", "sensor_id")
                      if k in fields]
    context_order = [k for k in ("i2s", "firmware_version", "dsp_version",
                                  "hardware_version", "ble_fw_version") if k in fields]
    pairs = list(itertools.combinations(identity_order, 2))
    pairs += [(a, b) for a in identity_order for b in context_order]
    for left, right in pairs:
        for sep_name, sep in (("join", ""), ("colon", ":"), ("dash", "-"), ("pipe", "|")):
            for order, text in (("forward", fields[left] + sep + fields[right]),
                                ("reverse", fields[right] + sep + fields[left])):
                for kdf, key in _kdf_forms(text.encode()).items():
                    cands[f"{left}+{right}.{sep_name}.{order}.{kdf}"] = key
    return cands


def candidate_keys_from_firmware(fw_data: bytes, sig_hits: dict, span: int = 512) -> dict:
    """16/24/32-byte constants near cipher code, plus file checksums as seeds.

    We slide 16/24/32-byte windows over a region around each signature hit; the
    real round key is usually stored or expanded close to the cipher tables.
    """
    cands = {}
    regions = []
    for offs in sig_hits.values():
        for o in offs:
            regions.append((max(0, o - span), min(len(fw_data), o + span)))
    # Without a signature there is no evidence-based region to search. Sliding
    # across arbitrary opaque bytes creates thousands of unauditable candidates
    # and false-positive opportunities.
    if not regions:
        return {}
    seen = set()
    idx = 0
    for start, end in regions:
        for size in (16, 24, 32):
            for pos in range(start, end - size + 1, 4):  # word-aligned
                key = fw_data[pos : pos + size]
                if key in seen or key == bytes(size):
                    continue
                seen.add(key)
                cands[f"fw@0x{pos:X}/{size}"] = key
                idx += 1
    return cands


@dataclass
class RecoveryResult:
    firmware_triage: dict = field(default_factory=dict)
    signatures: dict = field(default_factory=dict)
    n_candidates: int = 0
    n_derivations: int = 0
    best: dict | None = None
    hits: list = field(default_factory=list)
    conclusion: str = ""


def verify_key(bodies, headers, key: bytes, modes=MODES, iv_schemes=IV_SCHEMES,
               prescreen: float = 0.55) -> dict | None:
    """Best (mode, iv) for ``key``, corroborated across several blobs.

    ``bodies``/``headers`` are parallel lists.  The best (mode, iv) is chosen on
    the first body; a real key must then decrypt the *other* bodies too, so the
    reported score is the minimum across all bodies for that (mode, iv).  A key
    that only fluked one blob collapses to its worst blob and is rejected.  The
    cross-blob step runs only when the first blob already looks promising, so
    the common all-fail case stays cheap.
    """
    if isinstance(bodies, (bytes, bytearray)):
        bodies, headers = [bodies], [headers]
    best = None
    for mode in modes:
        schemes = ("zero",) if mode == "ECB" else iv_schemes
        for scheme in schemes:
            try:
                plain0 = decode.decrypt(bodies[0], key, mode=mode, iv=scheme, header=headers[0])
            except Exception:
                continue
            s0 = decode.plaintext_score(plain0)
            score = s0["score"]
            if score >= prescreen and len(bodies) > 1:
                worst = score
                for body, hdr in zip(bodies[1:], headers[1:]):
                    try:
                        p = decode.decrypt(body, key, mode=mode, iv=scheme, header=hdr)
                    except Exception:
                        worst = 0.0
                        break
                    worst = min(worst, decode.plaintext_score(p)["score"])
                score = worst
            if best is None or score > best["score"]:
                best = {**s0, "score": score, "single_score": s0["score"], "mode": mode, "iv": scheme}
    return best


def recover(scans: list[dict], firmware_blobs: dict | None = None,
            device: dict | None = None, score_threshold: float = 0.6,
            workers: int = 1) -> RecoveryResult:
    """Attempt key recovery.

    ``scans``          list of ``{"blobs": {key: raw_bytes}, "device": {...}}``.
    ``firmware_blobs`` output of :func:`scio.firmware.load_blob_dir` (optional).
    ``device``         identifiers (falls back to the first scan's ``device``).
    """
    result = RecoveryResult()
    if device is None and scans:
        device = scans[0].get("device", {})
    device = device or {}

    # Gather independent opaque bodies to reduce single-blob false positives.
    bodies, headers = [], []
    for sc in scans:
        for key in ("sample", "sample_dark", "sample_gradient", "sample_white"):
            blob = sc.get("blobs", {}).get(key)
            if blob:
                b = decode.split_blob(blob)
                bodies.append(b.body)
                headers.append(b.header)
        if len(bodies) >= 4:
            break
    if not bodies:
        result.conclusion = "no scan blobs supplied - nothing to verify against"
        return result

    # 1-2. Firmware triage + signatures.
    fw_data = None
    if firmware_blobs and "dsp_op" in firmware_blobs:
        fw_data = firmware_blobs["dsp_op"]["data"]
        result.firmware_triage = firmware.triage(firmware_blobs)
        result.signatures = find_signatures(fw_data)

    # 3. Candidate keys.
    candidates = candidate_keys_from_device(device)
    if fw_data is not None:
        candidates.update(candidate_keys_from_firmware(fw_data, result.signatures))
    result.n_derivations = len(candidates)
    # Many encodings collapse to the same bytes (notably numeric version
    # strings). Test each unique key once while retaining all provenance labels.
    by_key = {}
    for label, candidate in candidates.items():
        by_key.setdefault(candidate, []).append(label)
    unique_candidates = [(" | ".join(labels), candidate) for candidate, labels in by_key.items()]
    result.n_candidates = len(unique_candidates)

    # 4. Verify (corroborated across all gathered bodies).
    def evaluate(item):
        label, key = item
        return label, key, verify_key(bodies, headers, key)

    if workers > 1:
        pool = ThreadPoolExecutor(max_workers=workers)
        evaluated = pool.map(evaluate, unique_candidates)
    else:
        pool = None
        evaluated = map(evaluate, unique_candidates)
    for label, key, best in evaluated:
        if best is None:
            continue
        if result.best is None or best["score"] > result.best["score"]:
            result.best = {"label": label, "key": key.hex(), **best}
        if best["score"] >= score_threshold:
            result.hits.append({"label": label, "key": key.hex(), **best})
    if pool is not None:
        pool.shutdown()

    result.hits.sort(key=lambda h: -h["score"])

    # Conclusion.
    if result.hits:
        result.conclusion = f"candidate key found: {result.hits[0]['label']} (score {result.hits[0]['score']:.2f})"
    elif fw_data is None:
        result.conclusion = ("no local firmware/table body supplied; the tested identifier, serial and "
                             "version derivations produced no validated AES candidate. Other transform "
                             "families remain unresolved.")
    elif result.firmware_triage.get("dsp_op", {}).get("verdict", "").startswith("high-entropy"):
        result.conclusion = ("dsp_op is high-entropy and opaque; encryption, compression and packing "
                             "remain unresolved. No identifier/firmware candidate passed the oracle.")
    else:
        result.conclusion = ("firmware looks like plaintext but no automatic key candidate worked; "
                             "disassemble dsp_op (see dev/notebooks/02_scio_keyrecovery.ipynb) and add the constant/derivation found.")
    return result
