import struct

import numpy as np
from scio_offline import dex_refs, gradient, size_constraints


def test_dex_scanner_finds_const_string_and_sget():
    code = (struct.pack("<BBH", 0x1A, 0, 7) + struct.pack("<BBH", 0x62, 1, 3)
            + struct.pack("<BBI", 0x1B, 2, 9) + b"\x0e\x00")
    hits = list(dex_refs.scan_code(code, 0, len(code), {7, 9}, {3}))
    assert [(op, idx) for _, op, idx in hits] == [(0x1A, 7), (0x62, 3), (0x1B, 9)]
    assert not list(dex_refs.scan_code(code, 0, len(code), {8}, {4}))


def test_uleb_and_dex_header_rejection():
    assert dex_refs.uleb(bytes([0xE5, 0x8E, 0x26]), 0) == (624485, 3)
    try:
        dex_refs.Dex(b"not a dex" + bytes(200))
    except ValueError:
        pass
    else:
        raise AssertionError("non-DEX accepted")


def test_gradient_stats_flag_structure_and_derivation():
    rng = np.random.default_rng(1)
    random = [bytes(8) + rng.bytes(256) for _ in range(40)]
    assert gradient.role_stats(random)["positions_beyond_4_sigma"] == 0
    structured = [bytes(8) + bytes(16) + b[24:] for b in random]
    assert gradient.role_stats(structured)["longest_constant_run"] >= 16
    derived = [bytes(8) + bytes(x ^ 1 for x in b[8:]) for b in random]
    res = gradient.same_vs_other(derived, random)
    assert res["same_scan_mean"] < 0.2 and res["z"] < -5
    assert abs(gradient.same_vs_other(random[::-1], random)["same_scan_mean"] - 0.5) < 0.02


def test_size_constraints_known_facts():
    assert size_constraints.factorise(1714) == {2: 1, 857: 1}
    centers = size_constraints.splits(96)
    assert {"prefix": 0, "width": 8, "count": 12, "per_receptor": 1, "multiple_of_bands": False} in centers
    for n in (1714, 96, 140, 1166, 1792, 1648, 1408):
        assert not any(x["multiple_of_bands"] for x in size_constraints.splits(n))
    for n in (1792, 1648, 1408):
        assert not any(x["per_receptor"] for x in size_constraints.splits(n) if x["width"] >= 2)
    assert size_constraints.report()["cross_generation"]["gradient_difference_bytes"] == 240
