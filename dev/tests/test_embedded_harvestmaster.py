import importlib.util
from pathlib import Path
import sys
import zlib
import pytest
import io
import zipfile

SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'
sys.path.insert(0, str(SCRIPTS))
import inspect_harvestmaster_resx as assets
spec = importlib.util.spec_from_file_location('embedded_audit', SCRIPTS / 'audit_embedded_harvestmaster.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

def packed(data):
    c = zlib.compressobj(wbits=-15)
    return c.compress(data) + c.flush()

def test_exact_costura_recovery():
    planted = bytes(range(256)) * 30
    assert m.inflate(packed(planted)) == planted

def test_costura_bounds():
    with pytest.raises(ValueError): m.inflate(packed(b'x' * 1000), 100)

def test_costura_complete_boundaries():
    blob = packed(b'known assembly data' * 100)
    with pytest.raises(ValueError): m.inflate(blob[:-1])
    with pytest.raises(ValueError): m.inflate(blob + b'garbage')

def test_no_escape_write():
    with pytest.raises(ValueError): m.write_new('../escape', b'x')

def test_resx_bytearray_exact():
    rows = list(assets.parse_resx(b'<root><data name="asset" type="System.Byte[]"><value>YWJj</value></data></root>'))
    assert rows[0][1] == b'abc'

def test_resx_bad_base64_and_entities():
    with pytest.raises(ValueError): list(assets.parse_resx(b'<!DOCTYPE root><root/>'))
    with pytest.raises(ValueError): list(assets.parse_resx(b'<root><data type="System.Byte[]"><value>!!!</value></data></root>'))

def test_nested_zip_bounds():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w') as z: z.writestr('asset.bin', b'abc')
    assert list(assets.zip_entries(buf.getvalue())) == [('asset.bin', b'abc')]
    with pytest.raises(ValueError): list(assets.zip_entries(buf.getvalue(), 2))
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w') as z: z.writestr('../escape', b'x')
    with pytest.raises(ValueError): list(assets.zip_entries(buf.getvalue()))
