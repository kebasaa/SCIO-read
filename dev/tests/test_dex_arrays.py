import sys
import struct
from pathlib import Path
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from probe_dex_arrays import arrays


def fixture():
    raw=bytearray(512);raw[:8]=b'dex\n035\0'
    struct.pack_into('<I',raw,40,0x12345678)
    struct.pack_into('<IIII',raw,56,1,112,1,116)
    struct.pack_into('<II',raw,96,1,120)
    struct.pack_into('<I',raw,112,160)
    name=b'Lcom/consumerphysics/Test;'
    raw[160:160+len(name)+2]=bytes([len(name)])+name+b'\0'
    struct.pack_into('<I',raw,120+24,256)
    raw[256:264]=b'\0\0\1\0\0\0\x80\x03'
    struct.pack_into('<I',raw,384+12,40)
    raw[400:408]=b'\x26\0\4\0\0\0\0\0'
    struct.pack_into('<HHI',raw,408,0x300,1,64)
    raw[416:480]=bytes(range(64))
    return raw


def test_code_item_array_candidate():
    result=list(arrays(fixture()))
    assert len(result)==1 and result[0][1]==bytes(range(64))
    assert result[0][0]['class']=='Lcom/consumerphysics/Test;'
    assert result[0][0]['payload_offset']==408


def test_invalid_payload_boundaries():
    raw=fixture();struct.pack_into('<I',raw,412,1000)
    assert list(arrays(raw))==[]
    raw=fixture();struct.pack_into('<i',raw,402,-100000)
    assert list(arrays(raw))==[]
    raw=fixture();struct.pack_into('<I',raw,396,9999)
    with pytest.raises(ValueError):list(arrays(raw))
