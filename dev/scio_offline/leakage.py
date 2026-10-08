"""Supervised leakage test: do scan bodies carry information about the spectrum?

Every earlier statistic on the bodies was unsupervised (entropy, byte histograms,
positional uniformity, bit distance between repeat captures). Those cannot separate
encryption from a rate-filling proprietary coder. The paired corpus can: a
fixed-rate coder of sensor counts almost always leaves *some* body bits, bytes or
words correlated with the signal level (scale fields, DC terms, fixed-position
quantised values), whereas encryption under a fresh per-blob nonce leaves none.

Two detectors, both with permutation nulls that recompute the identical statistic
on shuffled targets, so the reported p-values already account for scanning every
feature (max-statistic) and every ridge penalty (max over the grid):

* ``univariate_scan``: max |Pearson r| between any feature column and the target.
* ``grouped_ridge``: pooled held-out R^2 of dual-form ridge regression under
  leave-one-group-out cross-validation.

Targets are permuted *within* acquisition groups, so neither detector can be fooled
by a per-acquisition body property (a date or counter field) that happens to
co-vary with the group's spectra.

``power_check`` runs both detectors on synthetic fixtures of the real corpus's size:
a fixed-position "codec" at decreasing leakage strength, and the same plaintexts
under a SHA-256 counter keystream with a fresh nonce. A negative real result is
only interpretable relative to that measured power.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np

from . import research

HEADER = 8
VIEWS = ("bits", "bytes", "u16le", "u16be")
FRESH_MANIFEST = (research.DEV / "analysis_output" / "recovery_20261003_followup"
                  / "fresh_reference_validation.json")


# -- corpus -----------------------------------------------------------------
def frozen_hashes(path=FRESH_MANIFEST) -> set[str]:
    """SHA-256 of every blob reserved for prospective confirmation."""
    path = Path(path)
    if not path.exists():
        return set()
    return {b["sha256"] for b in json.loads(path.read_text(encoding="utf-8"))["blobs"]}


def _kept(rows, frozen):
    rows = research.contexts() if rows is None else rows
    frozen = frozen_hashes() if frozen is None else frozen
    kept, dropped = [], 0
    for r in rows:
        if any(hashlib.sha256(v).hexdigest() in frozen for v in r["blobs"].values()):
            dropped += 1
            continue
        kept.append(r)
    return kept, dropped


def corpus_groups(rows=None, frozen=None) -> dict:
    """Records grouped by ``device_id`` (frozen blobs excluded).

    Different devices are different sensors/generations and must not be stacked
    into one feature matrix, so leakage runs per group.
    """
    kept, _ = _kept(rows, frozen)
    groups = {}
    for r in kept:
        groups.setdefault(r["device"].get("device_id"), []).append(r)
    return groups


def load_corpus(rows=None, frozen=None, device_id=None) -> dict:
    """Paired corpus for ONE device and blob geometry, frozen blobs excluded.

    With several devices present, ``device_id`` selects the group; the default is
    the largest (the owner's own unit). Use :func:`corpus_groups` to list devices.
    """
    kept_all, dropped = _kept(rows, frozen)
    groups = {}
    for r in kept_all:
        groups.setdefault(r["device"].get("device_id"), []).append(r)
    if not groups:
        raise ValueError("no records after frozen exclusion")
    if device_id is None:
        device_id = max(groups, key=lambda d: len(groups[d]))
    kept = groups[device_id]
    shapes = {(len(r["blobs"]["sample"]), len(r["blobs"]["sample_dark"])) for r in kept}
    if len(shapes) != 1:
        raise ValueError(f"device {device_id} mixes blob sizes {shapes}")
    return {
        "rows": kept,
        "device_id": device_id,
        "n": len(kept),
        "spectra": np.array([r["truth"]["reflectance"] for r in kept], float),
        "wavelength_nm": np.asarray(kept[0]["truth"]["wavelength_nm"], float),
        "acquisition_group": np.array([r["acquisition_group"] for r in kept]),
        "white_group": np.array([r["white_group"] for r in kept]),
        "frozen_excluded": dropped,
    }


def targets(spectra: np.ndarray, wavelength: np.ndarray) -> dict[str, np.ndarray]:
    """Scalar spectral summaries a sample-domain coder would have to carry."""
    spectra = np.asarray(spectra, float)
    x = (wavelength - wavelength.mean()) / np.ptp(wavelength)
    centred = spectra - spectra.mean(0)
    _, _, vt = np.linalg.svd(centred, full_matrices=False)
    out = {"mean": spectra.mean(1),
           "log_mean": np.log(np.clip(spectra.mean(1), 1e-12, None)),
           "slope": np.polyfit(x, spectra.T, 1)[0]}
    for k in range(min(3, vt.shape[0])):
        out[f"pc{k + 1}"] = centred @ vt[k]
    return out


def features(blob: bytes, view: str) -> np.ndarray:
    """One feature vector from the body after the 8-byte header."""
    body = np.frombuffer(blob[HEADER:], dtype=np.uint8)
    if view == "bits":
        return np.unpackbits(body).astype(float)
    if view == "bytes":
        return body.astype(float)
    if view in ("u16le", "u16be"):
        if body.size % 2:
            raise ValueError("odd body length cannot form u16 words")
        return np.frombuffer(body.tobytes(), dtype="<u2" if view == "u16le" else ">u2").astype(float)
    raise ValueError(f"unknown view {view!r}")


def matrix(blobs, view: str) -> np.ndarray:
    return np.vstack([features(b, view) for b in blobs])


# -- statistics -------------------------------------------------------------
def _standardise(X: np.ndarray) -> np.ndarray:
    X = np.asarray(X, float)
    sd = X.std(0)
    keep = sd > 0
    return (X[:, keep] - X[:, keep].mean(0)) / sd[keep]


def permutations(y: np.ndarray, groups, n_perm: int, seed: int) -> np.ndarray:
    """``n_perm`` copies of y, each shuffled within every group (columns)."""
    rng = np.random.default_rng(seed)
    y = np.asarray(y, float)
    groups = np.asarray(groups)
    out = np.empty((y.size, n_perm))
    index = [np.flatnonzero(groups == g) for g in np.unique(groups)]
    for j in range(n_perm):
        col = y.copy()
        for idx in index:
            col[idx] = y[rng.permutation(idx)]
        out[:, j] = col
    return out


def _p_value(observed: float, null: np.ndarray) -> float:
    return float((1 + np.sum(null >= observed)) / (1 + null.size))


def _max_abs_r(Z: np.ndarray, Y: np.ndarray) -> np.ndarray:
    """max over features of |r| for every column of Y."""
    Yz = (Y - Y.mean(0)) / Y.std(0)
    return np.concatenate([np.abs(Z.T @ Yz[:, i:i + 256] / Z.shape[0]).max(0)
                           for i in range(0, Yz.shape[1], 256)])


def univariate_scan(X, y, groups, n_perm: int = 1000, seed: int = 0) -> dict:
    Z = _standardise(X)
    y = np.asarray(y, float)
    observed = float(_max_abs_r(Z, y[:, None])[0])
    r = Z.T @ ((y - y.mean()) / y.std()) / Z.shape[0]
    null = _max_abs_r(Z, permutations(y, groups, n_perm, seed))
    return {"statistic": "max_abs_pearson", "observed": observed,
            "best_feature": int(np.argmax(np.abs(r))), "n_features": int(Z.shape[1]),
            "p_value": _p_value(observed, null),
            "null_quantiles": {q: float(np.quantile(null, q)) for q in (0.5, 0.95, 0.99)}}


def logo_folds(groups):
    groups = np.asarray(groups)
    for g in np.unique(groups):
        test = groups == g
        yield np.flatnonzero(~test), np.flatnonzero(test)


def _ridge_r2(K: np.ndarray, Y: np.ndarray, folds, alphas) -> np.ndarray:
    """Pooled held-out R^2 per (alpha, column of Y), dual-form ridge on a linear kernel."""
    pred = np.zeros((len(alphas),) + Y.shape)
    for train, test in folds:
        Ktt = K[np.ix_(train, train)]
        Kst = K[np.ix_(test, train)]
        mu = Y[train].mean(0)
        for a, alpha in enumerate(alphas):
            coef = np.linalg.solve(Ktt + alpha * np.eye(train.size), Y[train] - mu)
            pred[a, test] = Kst @ coef + mu
    sst = ((Y - Y.mean(0)) ** 2).sum(0)
    return 1 - ((pred - Y) ** 2).sum(1) / sst


def grouped_ridge(X, y, groups, alphas=None, n_perm: int = 1000, seed: int = 0) -> dict:
    Z = _standardise(X)
    K = Z @ Z.T / Z.shape[1]
    alphas = list(alphas or (1e-3, 1e-2, 1e-1, 1.0, 10.0))
    folds = list(logo_folds(groups))
    y = np.asarray(y, float)
    observed_grid = _ridge_r2(K, y[:, None], folds, alphas)[:, 0]
    null = _ridge_r2(K, permutations(y, groups, n_perm, seed), folds, alphas).max(0)
    observed = float(observed_grid.max())
    return {"statistic": "max_over_alpha_logo_r2", "observed": observed,
            "r2_by_alpha": dict(zip(map(str, alphas), map(float, observed_grid))),
            "folds": len(folds), "p_value": _p_value(observed, null),
            "null_quantiles": {q: float(np.quantile(null, q)) for q in (0.5, 0.95, 0.99)}}


# -- synthetic power check --------------------------------------------------
def _keystream(nonce: bytes, size: int) -> bytes:
    out = bytearray()
    counter = 0
    while len(out) < size:
        out += hashlib.sha256(nonce + counter.to_bytes(4, "little")).digest()
        counter += 1
    return bytes(out[:size])


def synthetic_corpus(n: int, body: int, fields: int, seed: int, groups: int = 3):
    """Fixed-position u16 codec fixture and its encrypted twin.

    ``fields`` u16 words carry the binned signal (quantised, with sensor noise);
    the rest of the body is random fill. The encrypted twin XORs the identical
    plaintext with a SHA-256 counter keystream under a fresh random nonce.
    """
    rng = np.random.default_rng(seed)
    level = rng.lognormal(-1.0, 0.8, n)
    shape = rng.normal(0, 0.05, (n, 1)) * np.linspace(-1, 1, max(fields, 1))
    signal = level[:, None] * (1 + shape) + rng.normal(0, 0.01, (n, max(fields, 1)))
    counts = np.clip(signal / signal.max() * 60000, 0, 65535).astype("<u2")
    group = np.repeat(np.arange(groups), -(-n // groups))[:n]
    codec, cipher = [], []
    for i in range(n):
        plain = bytearray(rng.bytes(body))
        words = counts[i, :fields].tobytes()
        plain[:len(words)] = words
        codec.append(bytes(HEADER) + bytes(plain))
        ks = _keystream(rng.bytes(16), body)
        cipher.append(bytes(HEADER) + bytes(p ^ k for p, k in zip(plain, ks)))
    return {"codec": codec, "cipher": cipher, "target": level, "groups": group}


def power_check(n: int, body: int, fields_grid=(896, 64, 8, 1), n_perm: int = 500,
                seed: int = 0, alpha: float = 0.01) -> dict:
    """Detection rates of both detectors on the codec fixture vs the cipher twin."""
    rows = []
    for fields in fields_grid:
        fx = synthetic_corpus(n, body, fields, seed + fields)
        entry = {"fields": int(fields)}
        for kind in ("codec", "cipher"):
            res = {}
            for view in ("bits", "u16le"):
                X = matrix(fx[kind], view)
                res[view] = {
                    "univariate_p": univariate_scan(X, fx["target"], fx["groups"], n_perm, seed)["p_value"],
                    "ridge_p": grouped_ridge(X, fx["target"], fx["groups"], n_perm=n_perm, seed=seed)["p_value"],
                }
            res["detected"] = any(min(v.values()) < alpha for v in res.values() if isinstance(v, dict))
            entry[kind] = res
        rows.append(entry)
    detected = [r["fields"] for r in rows if r["codec"]["detected"]]
    return {"n": n, "body_bytes": body, "alpha": alpha, "n_perm": n_perm, "rows": rows,
            "smallest_detected_fields": min(detected) if detected else None,
            "cipher_false_positives": sum(r["cipher"]["detected"] for r in rows)}
