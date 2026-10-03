import struct
import sys
from pathlib import Path
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from audit_dex_boundary import definitions, uleb


def test_uleb_bounds():
    assert uleb(b'\x81\x01', 0) == (129, 2)
    with pytest.raises(ValueError):
        uleb(b'\x80', 0)
    with pytest.raises(ValueError):
        uleb(b'\x80' * 5, 0)


def test_definition_not_just_string_reference():
    name = b'Landroid/hardware/ISCiO;'
    raw = bytearray(152) + bytes([len(name)]) + name + b'\0'
    raw[:8] = b'dex\n035\0'
    struct.pack_into('<I', raw, 40, 0x12345678)
    struct.pack_into('<4I', raw, 56, 1, 112, 1, 116)
    struct.pack_into('<2I', raw, 96, 1, 120)
    struct.pack_into('<I', raw, 112, 152)
    assert definitions(raw) == [name.decode()]
    struct.pack_into('<I', raw, 96, 0)
    assert definitions(raw) == []  # String remains, but class is not defined.


def test_invalid_header_rejected():
    with pytest.raises(ValueError):
        definitions(b'dex\n035\0')
