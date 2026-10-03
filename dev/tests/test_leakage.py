import numpy as np
from scio_offline import leakage as L


def test_codec_fixture_detected_and_cipher_twin_not():
    fx = L.synthetic_corpus(60, 1792, 8, seed=5)
    for kind, expect in (("codec", True), ("cipher", False)):
        X = L.matrix(fx[kind], "u16le")
        p = L.univariate_scan(X, fx["target"], fx["groups"], 199, seed=1)["p_value"]
        assert (p < 0.01) is expect


def test_ridge_detects_distributed_leak():
    fx = L.synthetic_corpus(60, 512, 256, seed=9)
    X = L.matrix(fx["codec"], "u16le")
    assert L.grouped_ridge(X, fx["target"], fx["groups"], n_perm=199, seed=2)["p_value"] < 0.01


def test_p_values_in_range():
    rng = np.random.default_rng(0)
    X, y, g = rng.random((30, 20)), rng.random(30), np.repeat([0, 1, 2], 10)
    for res in (L.univariate_scan(X, y, g, 99), L.grouped_ridge(X, y, g, n_perm=99)):
        assert 1 / 100 <= res["p_value"] <= 1


def test_feature_views_shapes():
    blob = bytes(8) + bytes(range(256)) * 7
    assert L.features(blob, "bits").shape == (14336,)
    assert L.features(blob, "bytes").shape == (1792,)
    assert L.features(blob, "u16le").shape == (896,)
    assert L.features(blob, "u16be")[0] == 0x0001 and L.features(blob, "u16le")[0] == 0x0100


def test_permutations_stay_within_groups():
    y = np.arange(12.0)
    g = np.repeat(["a", "b", "c"], 4)
    P = L.permutations(y, g, 20, seed=3)
    for grp in "abc":
        idx = g == grp
        assert all(set(P[idx, j]) == set(y[idx]) for j in range(20))


def test_logo_folds_disjoint():
    g = np.array([0, 0, 1, 1, 2, 2, 2])
    folds = list(L.logo_folds(g))
    assert len(folds) == 3
    for train, test in folds:
        assert not set(g[train]) & set(g[test])


def test_frozen_blobs_excluded():
    import hashlib
    rows = [{"blobs": {"sample": bytes([i]) * 1800, "sample_dark": bytes(1800)},
             "device": {"device_id": "X"}, "acquisition_group": "d", "white_group": "w",
             "truth": {"reflectance": [0.5, 0.6], "wavelength_nm": [740, 741]}} for i in (1, 2)]
    frozen = {hashlib.sha256(bytes([1]) * 1800).hexdigest()}
    c = L.load_corpus(rows, frozen)
    assert len(c["rows"]) == 1 and c["frozen_excluded"] == 1
