import sys
from pathlib import Path
import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from probe_arm32_strings import read_var,read_ref,encode_ref,encode_unsigned,pool_entries
from trace_arm32_diagnostics import pool_load,segments,direct_calls
import struct


def test_distinct_integer_byte_orders():
    for value in (0,1,127,128,18921,138149,0xfffffff):
        encoded=encode_unsigned(value)
        assert read_var(encoded,0)==(value,len(encoded))
        encoded=encode_ref(value)
        assert read_ref(encoded,0)==(value,len(encoded))
    assert encode_unsigned(128)==b'\x00\x81'
    assert encode_ref(128)==b'\x01\x80'
    assert read_var(b'\xbf',0,192)==(-1,1)


def test_pool_framing_and_rejections():
    data=b'\x11'+encode_ref(18921)+b'\x00\xc0\x02\x40\x60\x80'
    assert pool_entries(data,0,6,138149)==([18921,None,None,None,None,None],len(data))
    for bad in (b'',b'\x11',b'\x11\x01',b'\x20',b'\x4f'):
        with pytest.raises(ValueError):pool_entries(bad,0,1,138149)
    with pytest.raises(ValueError):pool_entries(b'\x11'+encode_ref(200000),0,1,138149)
    with pytest.raises(ValueError):read_var(b'\0'*5,0)
    with pytest.raises(ValueError):encode_unsigned(-1)


def test_arm32_tagged_pool_load():
    assert pool_load(0xe2852a0e,0xe592220f)==0xe20f
    assert pool_load(0xe2852a0e,0xe5922217)==0xe217
    assert pool_load(0xe2852a0e,0xe5932217) is None
    assert pool_load(0xe2852a0e,0x15922217) is None
    assert pool_load(0xe2842a0e,0xe5922217) is None
    with pytest.raises(ValueError):list(segments(b'not ELF'))


def test_arm32_direct_calls():
    code=struct.pack('<IIII',0xeb000002,0xebfffffd,0x9b000000,0xfa000000)
    assert list(direct_calls(code,0x1000))==[(0x1000,0x1010),(0x1004,0x1000),(0x1008,0x1010)]
    with pytest.raises(ValueError):list(direct_calls(b'\0'))
    with pytest.raises(ValueError):list(direct_calls(b'\0'*4,1))
