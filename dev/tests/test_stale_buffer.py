import importlib
import base64
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
sb = importlib.import_module("probe_stale_buffer")


def _rand(seed, n):
    import random
    rnd = random.Random(seed)
    return bytes(rnd.randrange(256) for _ in range(n))


def test_planted_same_offset_residue_is_found():
    grad = _rand(1, 1416)
    reply = bytearray(16)
    reply[0:8] = b"\x50\x00\x64\x01\x00\x00\x10\x0f"     # battery fields
    reply[13:16] = grad[13:16]                            # the reported residue
    reply[8:13] = b"\x00" * 5
    res = sb.analyse([{"probe": "battery", "reply": bytes(reply), "prev_scan": {"gradient": grad},
                       "session_blobs": [grad]}], {"battery": [bytes(16)]})
    pos = res["per_probe"]["battery"]["same_offset_positions"]
    assert {13, 14, 15} <= set(pos)
    assert res["unexplained_padding_bytes"] == 0


def test_untransmitted_padding_is_flagged():
    grad = _rand(2, 1416)
    reply = bytes(8) + _rand(99, 8)                      # padding seen nowhere
    res = sb.analyse([{"probe": "battery", "reply": reply, "prev_scan": {"gradient": grad},
                       "session_blobs": [grad]}], {"battery": [bytes(16)]})
    assert res["unexplained_padding_bytes"] > 0
    assert res["verdict"].startswith("UNEXPLAINED")


def test_bytes_from_an_earlier_blob_count_as_transmitted():
    old = _rand(3, 1800)
    reply = bytes(8) + old[500:508]
    res = sb.analyse([{"probe": "battery", "reply": reply, "prev_scan": {"gradient": _rand(4, 1416)},
                       "session_blobs": [old]}], {"battery": []})
    assert res["per_probe"]["battery"]["padding_classes"] == {"in_blobs": 8}


def test_adjacent_matches_must_belong_to_one_blob():
    assert sb.classify(b"AB", {"dark": b"AX", "sample": b"YB"}, set(), []) == [
        "unexplained", "unexplained"]


def test_single_byte_match_is_not_origin_proof():
    assert sb.classify(b"A", {"gradient": b"A"}, set(), []) == ["unexplained"]


def _saved_run():
    blob = bytes(range(16))
    return {"scans_b64": [{"gradient": base64.b64encode(blob).decode()}] * 2,
            "baseline": {}, "errors": [], "replies": [
                {"probe": "battery", "context": "r0:scan->battery", "hex": blob.hex()}]}


def test_replay_reports_missing_coverage(tmp_path):
    path = tmp_path / "rounds.json"
    path.write_text(json.dumps(_saved_run()))
    res = sb.replay(path)
    assert len(res["missing_reply_contexts"]) == 2
    assert "ble_config" in res["unobserved_probes"]
    assert res["battery_tail"]["byte15_equals_prev_blob_byte15"] == {"gradient": 1}
    assert res["baseline_counts"]["battery"] == 0


@pytest.mark.parametrize("context", ["r9:scan->battery", "r0:scan->ble_id", "bad"])
def test_replay_rejects_incorrect_scan_association(tmp_path, context):
    data = _saved_run()
    data["replies"][0]["context"] = context
    path = tmp_path / "rounds.json"
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError):
        sb.replay(path)


def test_replay_does_not_match_future_scans(tmp_path):
    data = _saved_run()
    data["scans_b64"][0] = {"gradient": base64.b64encode(b"x" * 16).decode()}
    path = tmp_path / "rounds.json"
    path.write_text(json.dumps(data))
    result = sb.replay(path)
    assert result["per_probe"]["battery"]["padding_classes"] == {"unexplained": 8}


def test_saved_owner_evidence_reproduces_counts():
    path = Path(__file__).resolve().parents[1] / "analysis_output/stale_buffer_20261028/rounds.json"
    result = sb.replay(path)
    assert result["n_scans"] == 20 and result["n_replies"] == 29
    assert result["battery_tail"] == {"n_battery_replies": 20,
        "byte15_equals_prev_blob_byte15": {"gradient": 20}}
    assert result["missing_reply_contexts"] == ["r5:scan->ble_config"]
    assert result["unobserved_probes"] == ["ble_config"]
    assert result["unexplained_padding_bytes"] > 0
    assert len(result["capture_errors"]) == 1
