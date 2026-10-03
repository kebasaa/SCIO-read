"""Guard read-only native triage, especially missing-literal offset handling."""
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'
sys.path.insert(0, str(SCRIPTS))
from audit_native_paths import occurrences, snapshot_header


def test_missing_anchor_has_no_offsets():
    import pytest
    with pytest.raises(ValueError):
        list(occurrences(b'abcdef', b''))
    assert list(occurrences(b'abcdef', b'absent')) == []
    assert list(occurrences(b'foo foo', b'foo')) == [0, 4]


def test_snapshot_header_identification():
    import struct
    version = b'a' * 32
    raw = b'\xf5\xf5\xdc\xdc' + struct.pack('<QQ', 100, 3) + version + b'arm android\0'
    section = {'address': 4096, 'offset': 0, 'size': len(raw), 'type': 1}
    result = snapshot_header(raw, {'value': 4096, 'size': len(raw)}, [section])
    assert result['snapshot_format_hash'] == version.decode()
    assert result['feature_string'] == 'arm android'
    assert snapshot_header(b'\0' * len(raw), {'value': 4096, 'size': len(raw)}, [section]) is None
