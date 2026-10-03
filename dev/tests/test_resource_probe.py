import base64
import bz2
import gzip
import lzma
import zlib
import pytest
from scio_offline.resource_probe import decompress,encoded_runs,java_constants


@pytest.mark.parametrize('kind,encode',[('gzip',gzip.compress),('zlib',zlib.compress),('bzip2',bz2.compress),('xz',lzma.compress)])
def test_bounded_streams(kind,encode):
    original=b'example firmware bytes'*100
    data=encode(original)
    assert decompress(data+b'trailer',kind)==(original,len(data))
    with pytest.raises(ValueError):decompress(data,kind,32)
    with pytest.raises((ValueError,EOFError)):decompress(data[:-2],kind)


def test_code_literals_without_execution():
    raw=bytes(range(128));encoded=base64.b64encode(raw)
    assert list(encoded_runs(encoded))[0][2]==raw
    assert list(java_constants('String x="'+encoded.decode()+'";'))[0][2]==raw
    source='new byte[]{'+','.join(str(x-128) for x in range(128))+'}'
    assert list(java_constants(source))[0][2]==bytes(range(128,256))
    assert not list(java_constants('new byte[]{'+','.join(['run()']*128)+'}'))
    assert any(kind=='hex-run' and data==raw for _,kind,data in encoded_runs(raw.hex().encode()))
