import importlib
import sys
import zlib
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
audit = importlib.import_module("verify_research_summary")


@pytest.mark.parametrize("wbits", [15, 31, -15])
def test_complete_stream_requires_eof_without_trailing_bytes(wbits):
    compressor = zlib.compressobj(wbits=wbits)
    stream = compressor.compress(bytes(range(256)) * 4) + compressor.flush()
    assert audit.complete_stream(stream, wbits)
    assert not audit.complete_stream(stream[:-1], wbits)
    assert not audit.complete_stream(stream + b"trailer", wbits)


def test_correct_aes_key_can_fail_repeatability_screen():
    result = audit.repeatability_counterexample()
    assert result["exact_decrypt_and_decompress"]
    assert result["signal_repeatability"]["score"] > .99
    assert result["correct_plaintext_repeatability"]["score"] < .1
    assert result["existing_detector_with_correct_key"]["repeatability"] < .5
