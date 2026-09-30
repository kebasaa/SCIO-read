"""Chosen-ciphertext probing of the decoding server.

The vendor server decodes whatever blob it is sent, deterministically (noise floor
exactly 0), and reports the result band by band. Flipping a bit in a blob and
watching *which bands move, by how much, and with what sign* exposes the structure
of the transform from outside the wire - something no offline statistic on the
ciphertext can do.

This module is the analysis half. It contains

* tamper helpers that edit one byte of one blob inside a request payload;
* :func:`delta`, which compares a tampered result with an untampered baseline;
* :func:`protocol` / :func:`run_protocol`, the fixed set of probes, written against
  an abstract ``oracle(payload) -> spectrum`` so the **same** protocol runs against
  the real server and against the simulator in ``malleability_sim``;
* :func:`classify`, which turns the observations into one label - or
  ``"undetermined"``.

Two rules govern the classifier, and both are enforced by tests rather than by a
comment:

1. **It may answer "undetermined" but never the wrong thing.** A wrong confident
   label is costlier than no label.
2. **It can never say "encryption excluded".** No probe from the client side can
   establish that; the device could encrypt and the server decrypt. The label set
   simply has no such member.

Why the signs matter: the binning is non-negative and (W - Wd) is positive, so the
sign of the change in a band equals the sign of the plaintext change. Flipping bit
*t* of a pixel moves it by +2^t if the bit was 0 and -2^t if it was 1, so in a
bit-malleable transform each flip leaks one plaintext bit. :func:`delta` therefore
keeps signs.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass, field

import numpy as np

from scio import store

N_PX = 896          # hypothesis only: 1792 B / 2 - see dev/README.md, correction 3
N_BANDS = 331
BODY = 1792
HEADER = 8
TOL = 1e-12          # "unchanged" means unchanged to this, not merely small

LABELS = (
    "stream",              # bit-malleable XOR/CTR/OFB-like, or a keyless mask
    "block_transform",     # linear, block-local (lossy DCT-like)
    "delta_coding",        # linear, damage carried to every later band
    "ecb_like",            # nonlinear, block-local
    "chained_block",       # CBC/CFB family: garbled block plus a linear neighbour
    "adaptive_stream",     # nonlinear, damage carried downstream (desync)
    "undetermined",
)


class OracleError(Exception):
    """The server refused or failed. The status and body are evidence."""

    def __init__(self, status: int, body: str = ""):
        super().__init__(f"HTTP {status}: {body[:120]}")
        self.status, self.body = status, body


# --------------------------------------------------------------------- tampering
def get_blob(payload: dict, key: str) -> bytearray:
    return bytearray(base64.b64decode("".join(payload[key].split())))


def set_blob(payload: dict, key: str, raw: bytes) -> dict:
    out = dict(payload)
    out[key] = store.wrap_b64(bytes(raw))
    return out


def tamper_bit(payload: dict, key: str, body_offset: int, bit: int) -> dict:
    """Flip one bit of the *body* (offset counted after the 8-byte header)."""
    raw = get_blob(payload, key)
    raw[HEADER + body_offset] ^= 1 << bit
    return set_blob(payload, key, raw)


def tamper_bits(payload: dict, key: str, flips: list) -> dict:
    """Several (body_offset, bit) flips in one request - for superposition tests."""
    raw = get_blob(payload, key)
    for off, bit in flips:
        raw[HEADER + off] ^= 1 << bit
    return set_blob(payload, key, raw)


# ------------------------------------------------------------------------- deltas
def delta(baseline, result, tol: float = TOL) -> dict:
    """How a tampered spectrum differs from the untampered one (signs kept)."""
    if result is None:
        return {"error": True, "changed": [], "n_changed": 0}
    b, r = np.asarray(baseline, float), np.asarray(result, float)
    d = r - b
    changed = np.flatnonzero(np.abs(d) > tol)
    return {
        "error": False,
        "delta": d,
        "changed": changed.tolist(),
        "n_changed": int(len(changed)),
        "first": int(changed[0]) if len(changed) else None,
        "last": int(changed[-1]) if len(changed) else None,
        "max_abs": float(np.max(np.abs(d))) if len(d) else 0.0,
    }


@dataclass
class Observation:
    label: str                      # human-readable probe id
    kind: str                       # ladder | pair | sweep | map
    params: dict
    status: int = 200
    spectrum: list | None = None
    body: str = ""
    d: dict = field(default_factory=dict)


# --------------------------------------------------------------------- the protocol
#: block A is mid-blob, block B a distant one; both far from the ends.
BLOCK_A, BLOCK_B = 50, 100
LADDER_BITS = (0, 1, 2, 3, 4)
DAMAGE_OFFSETS = (0, 1, 7, 8, 15, 16, 17, 800, 1775, 1791)


def protocol(role: str = "sample") -> list:
    """The probe specs, as data. Identical for the simulator and the real server."""
    a0 = BLOCK_A * 16 + 2            # a low-lane byte near the START of block A
    c0 = BLOCK_A * 16 + 14           # ... and one near its END
    b0 = BLOCK_B * 16 + 2
    specs = []
    for t in LADDER_BITS:                                        # bit-weight ladder
        specs.append({"id": f"ladder_a_b{t}", "kind": "ladder",
                      "flips": [(a0, t)], "role": role})
    # Why two positions: in CBC a flip garbles its own block and flips one bit in the
    # NEXT block at the same byte position. With ~2.7 pixels per band an early byte puts
    # that neighbour pixel right beside the garbled ones, so binning overlap contaminates
    # it; a late byte puts it 8 pixels away, clear of the garbled bands. CFB is the
    # mirror image (clean at the early byte). Each family needs one clean position.
    for t in LADDER_BITS:
        specs.append({"id": f"ladder_c_b{t}", "kind": "ladder",
                      "flips": [(c0, t)], "role": role})
    for t in LADDER_BITS:                                        # same, distant block
        specs.append({"id": f"ladder_b_b{t}", "kind": "ladder",
                      "flips": [(b0, t)], "role": role})
    specs.append({"id": "pair_ab_b3", "kind": "pair",            # superposition
                  "flips": [(a0, 3), (b0, 3)], "role": role})
    for k in range(16):                                          # sweep one whole block
        specs.append({"id": f"sweep_{k:02d}", "kind": "sweep",
                      "flips": [(BLOCK_A * 16 + k, 4)], "role": role})
    for off in DAMAGE_OFFSETS:                                   # damage map
        for t in (0, 7):
            specs.append({"id": f"map_{off}_b{t}", "kind": "map",
                          "flips": [(off, t)], "role": role})
    return specs


def run_protocol(oracle, payload: dict, *, role: str = "sample", specs=None,
                 on_observation=None):
    """Run the probes through ``oracle(payload) -> spectrum`` (may raise OracleError).

    Returns ``(observations, baseline)``; the baseline is requested first, *untampered*,
    in the same session - a tampered result is meaningless against a stale control.
    """
    def call(p):
        try:
            return 200, list(oracle(p)), ""
        except OracleError as exc:
            return exc.status, None, exc.body

    status, spec, body = call(payload)
    baseline = Observation("baseline", "baseline", {}, status, spec, body)
    if spec is None:
        return [], baseline
    obs = []
    for s in specs or protocol(role):
        p = tamper_bits(payload, s["role"], s["flips"])
        status, spec, body = call(p)
        o = Observation(s["id"], s["kind"], {"flips": s["flips"], "role": s["role"]},
                        status, spec, body, delta(baseline.spectrum, spec))
        obs.append(o)
        if on_observation:
            on_observation(o)
    return obs, baseline


# ------------------------------------------------------------------ classification
def _by_id(obs: list) -> dict:
    return {o.label: o for o in obs}


def _support(o) -> set:
    return set(o.d.get("changed", [])) if o is not None and o.status == 200 else set()


def _vec(o):
    return np.asarray(o.d["delta"], float) if o is not None and o.status == 200 and "delta" in o.d else None


def _jaccard(a: set, b: set) -> float:
    return len(a & b) / len(a | b) if (a or b) else 0.0


def _doubling_bands(ladder: list, rel: float = 1e-6) -> tuple:
    """Bands where |d(bit t+1)| / |d(bit t)| == 2 for the whole ladder.

    A bit-malleable (linear) transform satisfies this exactly: flipping bit t moves
    the plaintext by +/-2^t whatever the current value of that bit, so successive
    bits double in magnitude whatever their signs. A garbled block does not.
    """
    vecs = [_vec(o) for o in ladder]
    if any(v is None for v in vecs):
        return set(), set()
    support = set().union(*[set(np.flatnonzero(np.abs(v) > TOL).tolist()) for v in vecs])
    lin = set()
    for j in support:
        mags = [abs(v[j]) for v in vecs]
        if min(mags) <= TOL:
            continue
        if all(abs(mags[i + 1] / mags[i] - 2.0) <= rel * 2.0 for i in range(len(mags) - 1)):
            lin.add(j)
    return support, lin


def classify(obs: list, *, n_bands: int = N_BANDS) -> dict:
    """One label from :data:`LABELS`, with the evidence. Never a label meaning
    'encryption excluded': the set has no such member, by design."""
    ev = {"n_probes": len(obs)}

    def verdict(label, why):
        assert label in LABELS
        return {"label": label, "why": why, "evidence": ev}

    if not obs:
        return verdict("undetermined", "no observations")
    n_err = sum(1 for o in obs if o.status != 200)
    ev["errors"] = n_err
    if n_err > 0.5 * len(obs):
        # diffusion + a range check, a MAC/AEAD tag and plain rejection are
        # indistinguishable from outside, so this must never become "authenticated".
        return verdict("undetermined", f"{n_err}/{len(obs)} probes were rejected; "
                       "diffusion, a tag and a range check cannot be told apart")

    ob = _by_id(obs)
    ladder_a = [ob.get(f"ladder_a_b{t}") for t in LADDER_BITS]
    ladder_c = [ob.get(f"ladder_c_b{t}") for t in LADDER_BITS]
    ladder_b = [ob.get(f"ladder_b_b{t}") for t in LADDER_BITS]
    sup_a, lin_a = _doubling_bands(ladder_a)
    sup_c, lin_c = _doubling_bands(ladder_c)
    sup_b, lin_b = _doubling_bands(ladder_b)
    # The two positions inside block A are pooled: a mixed response (CBC/CFB) is clean
    # at only one of them, so the union is what shows a linear part beside a garbled one.
    sup, lin = sup_a | sup_c, lin_a | lin_c
    ladder = ladder_a
    if not sup:
        sup, lin, ladder = sup_b, lin_b, ladder_b
    ev["ladder"] = {"support": len(sup), "doubling_bands": len(lin)}
    if not sup:
        return verdict("undetermined", "no ladder flip moved any band: masked bits, dead "
                       "pixels or a rejected input - 'unchanged' is not 'ignored'")

    local = len(sup) <= 0.25 * n_bands
    frac_lin = len(lin) / len(sup)
    ev["linear_fraction"] = frac_lin
    ev["local"] = local

    sweep = [ob.get(f"sweep_{k:02d}") for k in range(16)]
    sw = [_support(o) for o in sweep]
    shared = float(np.median([_jaccard(sw[0], sw[15]), _jaccard(sw[0], sw[8]),
                              _jaccard(sw[1], sw[14]), _jaccard(sw[2], sw[13])]))
    ev["block_shared_jaccard"] = shared

    # Does damage run from the flip to the END of the spectrum, starting later the later
    # the flip? Judged on the HEAVY flips only: a Rice-style coder partly resynchronises,
    # so some flips stay local while others run on, and requiring every flip to run on
    # would miss exactly the coder it is meant to catch. Needs two or more distinct
    # starting bands, so a global effect (normalisation) - where every flip moves
    # everything from band 0 - cannot pass as desynchronisation.
    heavy = {}
    for o in obs:
        # single flips only: the two-flip superposition probe legitimately cancels in places
        if (o.kind != "pair" and o.status == 200
                and o.d.get("n_changed", 0) > 0.25 * n_bands):
            heavy[(int(o.params["flips"][0][0]), o.label)] = (o.d["first"], o.d["last"])
    by_off = sorted((off, f, l) for (off, _), (f, l) in heavy.items())
    firsts = [f for _, f, _ in by_off]
    downstream = bool(
        len(by_off) >= 2
        and all(l >= n_bands - 3 for _, _, l in by_off)
        and len(set(firsts)) >= 2
        and all(firsts[i] <= firsts[i + 1] for i in range(len(firsts) - 1)))
    ev["downstream"] = downstream
    ev["heavy_flips"] = len(by_off)
    # A locality claim has to survive the WHOLE protocol, not one ladder. The remainder
    # bits of a Rice code are exactly bit-malleable and local, so a few flips landing
    # there look like a stream cipher; the tell is that other flips desynchronise.
    any_heavy = len(by_off) > 0

    # How the damage scales with the bit's weight. A transform coder (however lossy) and any
    # bit-malleable scheme move the plaintext by an amount proportional to 2^t, so flipping
    # bit 4 does ~16x what bit 0 does. A garbled block does not: a block cipher replaces the
    # whole block with fresh random data whichever bit was flipped, so the ratio is ~1.
    # (An earlier draft used collinearity of the delta vectors; random ECB garbles share a
    # large common offset - random 16-bit pixels average ~32768 - and looked collinear.)
    ratios = []
    for lad in (ladder_a, ladder_c):
        v0, v4 = _vec(lad[0]), _vec(lad[-1])
        if v0 is None or v4 is None:
            continue
        n0, n4 = float(np.linalg.norm(v0)), float(np.linalg.norm(v4))
        if n4 > TOL:
            ratios.append(float("inf") if n0 <= TOL else n4 / n0)
    ratio = float(np.median(ratios)) if ratios else float("nan")
    ev["bit_weight_ratio"] = ratio
    weight_scaling = bool(ratios) and ratio >= 4.0
    garble_like = bool(ratios) and ratio <= 2.0

    # Sweeping one whole block: in ECB every byte garbles the SAME bands. Any residual
    # variation is a neighbouring pixel changing linearly - the signature of CBC/CFB - so an
    # ECB claim needs the sweep supports to agree almost exactly.
    live = [s for s in sw if s]
    sweep_min_j = min((_jaccard(a, b) for i, a in enumerate(live) for b in live[i + 1:]),
                      default=0.0) if len(live) >= 8 else 0.0
    ev["sweep_min_jaccard"] = sweep_min_j

    if frac_lin >= 0.9:                                     # ---- linear family
        pair, da, db = ob.get("pair_ab_b3"), _vec(ladder_a[3]), _vec(ladder_b[3])
        dp = _vec(pair)
        if dp is None or da is None or db is None:
            return verdict("undetermined", "superposition could not be checked")
        scale = max(np.max(np.abs(da)), np.max(np.abs(db)), TOL)
        if np.max(np.abs(dp - (da + db))) > 1e-9 * scale:
            return verdict("undetermined", "doubling holds but superposition fails")
        ev["superposition"] = True
        if downstream and da is not None and db is not None:
            common = np.flatnonzero((np.abs(da) > TOL) & (np.abs(db) > TOL))
            if len(common) >= 5:
                cos = float(np.dot(da[common], db[common]) /
                            (np.linalg.norm(da[common]) * np.linalg.norm(db[common])))
                ev["cosine_a_b"] = cos
                if abs(cos) > 0.98:
                    return verdict("delta_coding", "linear; damage runs to the last band and is "
                                   "collinear across distant flips")
        if any_heavy:
            return verdict("undetermined", "linear for some flips but others run downstream: a "
                           "desynchronising coder, or a mixed transform")
        if not local:
            return verdict("undetermined", "linear but not local (global normalisation?)")
        if shared >= 0.6:
            return verdict("block_transform", "linear and block-local: every byte of a block "
                           "moves the same bands")
        return verdict("stream", "linear, superposing, single-pixel support: a bit-malleable "
                       "stream (XOR/CTR/OFB-like) or a keyless mask")

    if frac_lin <= 0.1:                                     # ---- nonlinear family
        if downstream:
            return verdict("adaptive_stream", "nonlinear; damage starts at the flip and runs to "
                           "the end, moving later with the offset: desynchronisation")
        if any_heavy:
            return verdict("undetermined", "some flips run on but not consistently to the end")
        if local and weight_scaling and shared >= 0.6:
            return verdict("block_transform", "block-local and the damage scales with the bit's "
                           "weight: a lossy transform coder (rounding breaks exact doubling, "
                           "not the scaling)")
        if local and garble_like and sweep_min_j >= 0.9:
            return verdict("ecb_like", "block-local, damage independent of bit weight, and every "
                           "byte of the block garbles the same bands: a flip replaces its own "
                           "block and nothing else")
        return verdict("undetermined", "nonlinear but neither clearly block-local nor downstream")

    # ---- mixed: part of the damage is linear, part is not
    if any_heavy:
        return verdict("undetermined", "mixed response and some flips run downstream")
    if local and len(lin) >= 1 and (len(sup) - len(lin)) >= 2:
        return verdict("chained_block", "a garbled block plus a linear change beside it: the "
                       "CBC/CFB family")
    return verdict("undetermined", "mixed response that matches no known class")
