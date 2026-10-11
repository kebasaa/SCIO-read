"""Independently verify Vitaly's three raw-blob claims on the fw-138 batches.

Offline, on the raw ciphertext (no server). Checks, without trusting his numbers:
  (1) every per-blob nonce (header word1) is unique across all 300 blobs;
  (2) no keystream reuse: XOR of same-role bodies stays near full entropy
      (bit-balance ~0.5), and no two bodies are identical;
  (3) no positional leakage: zero byte positions are constant across the 25
      same-target scans; AND the cap-vs-wood single-session mean-difference
      "signal" dies under the session control (cap s1 vs cap s2) and a
      cross-session nearest-centroid classifier (train on session 1, test on
      session 2 -> chance), i.e. it was a session-confounded false alarm.

    python dev/scripts/probe_fw138_batch_leakage.py --output dev/analysis_output/<run>
"""
import argparse
import json
import sys
from pathlib import Path

import _bootstrap  # noqa: F401
import numpy as np
from scio_offline import research as r

sys.path.insert(0, str(r.DEV / "scripts"))
import ingest_fw138_batches as ib  # noqa: E402

ROLES = ("dark", "sample", "gradient")


def _mat(batches, target, session, role):
    for b in batches:
        if b["target"] == target and b["session"] == session:
            return np.array([np.frombuffer(s["frames"][role][8:], dtype=np.uint8) for s in b["scans"]])
    raise KeyError((target, session, role))


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    out = a.output.resolve()
    if not out.is_relative_to(r.DEV):
        raise ValueError("output under dev/ required")
    out.mkdir(parents=True, exist_ok=True)
    batches = ib.parse_all()

    # (1) nonce (word1) and word0 uniqueness across all blobs
    word1, word0 = [], []
    for b in batches:
        for s in b["scans"]:
            for role in ROLES:
                blob = s["frames"][role]
                word0.append(blob[0:4]); word1.append(blob[4:8])
    n = len(word1)
    claim1 = {"n_blobs": n, "unique_word1": len(set(word1)), "unique_word0": len(set(word0)),
              "all_word1_unique": len(set(word1)) == n, "word0_all_zero": set(word0) == {bytes(4)}}

    # (2) keystream reuse: same-target same-role same-session XOR bit-balance
    claim2 = {}
    for target in ("cap", "wood"):
        for role in ROLES:
            balances, identical = [], 0
            for sess in ("s1", "s2"):
                m = _mat(batches, target, sess, role)
                for i in range(len(m)):
                    for j in range(i + 1, len(m)):
                        x = np.bitwise_xor(m[i], m[j])
                        balances.append(np.unpackbits(x).mean())
                        if not x.any():
                            identical += 1
            claim2[f"{target}/{role}"] = {"pairs": len(balances),
                                          "bitbalance_mean": round(float(np.mean(balances)), 4),
                                          "bitbalance_min": round(float(np.min(balances)), 4),
                                          "bitbalance_max": round(float(np.max(balances)), 4),
                                          "identical_pairs": identical}

    # (3a) positional constancy across the 25 same-target scans (per session)
    claim3_const = {}
    for target in ("cap", "wood"):
        for role in ROLES:
            consts = []
            for sess in ("s1", "s2"):
                m = _mat(batches, target, sess, role)
                consts.append(int(np.sum((m == m[0]).all(axis=0))))
            claim3_const[f"{target}/{role}"] = {"const_positions_s1": consts[0], "const_positions_s2": consts[1]}

    # (3b) cap-vs-wood: single-session mean-diff "signal" vs session control vs cross-session classifier
    def meandiff_positions(A, B, sigma=5.0):
        # per-position Welch-ish z of mean difference; count |z|>sigma
        ma, mb = A.mean(0), B.mean(0)
        va, vb = A.var(0, ddof=1) / len(A), B.var(0, ddof=1) / len(B)
        sd = np.sqrt(va + vb) + 1e-9
        z = (ma - mb) / sd
        return int(np.sum(np.abs(z) > sigma)), float(np.max(np.abs(z)))

    def centroid_xval(role):
        cap1, cap2 = _mat(batches, "cap", "s1", role).astype(float), _mat(batches, "cap", "s2", role).astype(float)
        wood1, wood2 = _mat(batches, "wood", "s1", role).astype(float), _mat(batches, "wood", "s2", role).astype(float)
        c_cap, c_wood = cap1.mean(0), wood1.mean(0)            # centroids trained on session 1
        def acc(capX, woodX):
            def pred(x):
                return 0 if np.sum((x - c_cap) ** 2) < np.sum((x - c_wood) ** 2) else 1
            correct = sum(pred(x) == 0 for x in capX) + sum(pred(x) == 1 for x in woodX)
            return correct / (len(capX) + len(woodX))
        return {"train_sig_pos": meandiff_positions(cap1, wood1)[0],
                "train_max_z": round(meandiff_positions(cap1, wood1)[1], 2),
                "session_control_cap_s1_vs_s2_pos": meandiff_positions(cap1, cap2)[0],
                "cross_session_test_accuracy": round(acc(cap2, wood2), 3),
                "resubstitution_accuracy": round(acc(cap1, wood1), 3)}

    claim3_class = {role: centroid_xval(role) for role in ROLES}

    verdict = {
        "claim1_nonce_unique": claim1["all_word1_unique"],
        "claim2_no_keystream_reuse": all(v["bitbalance_min"] > 0.45 and v["identical_pairs"] == 0
                                         for v in claim2.values()),
        "claim3_no_positional_leak": all(v["const_positions_s1"] == 0 and v["const_positions_s2"] == 0
                                         for v in claim3_const.values()),
        "claim3_gradient_false_alarm_confirmed":
            claim3_class["gradient"]["cross_session_test_accuracy"] <= 0.65,
    }
    r.write_new(out / "batch_leakage.json", {
        "claim1": claim1, "claim2": claim2,
        "claim3_positional": claim3_const, "claim3_classifier": claim3_class,
        "verdict_vs_vitaly": verdict})
    print(json.dumps({"claim1": claim1, "verdict": verdict}, indent=1))
    for role in ROLES:
        print(role, claim3_class[role])


if __name__ == "__main__":
    main()
