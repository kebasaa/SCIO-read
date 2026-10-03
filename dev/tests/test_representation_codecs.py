import zlib
import pytest
from scio_offline.representation_codecs import probe, representations
from scio_offline.research import sha


@pytest.mark.parametrize('layout',['identity','swap16','swap32','reverse_bits_per_byte'])
def test_compressed_fixed_container_through_driver(layout):
    plain = bytes(range(256)) * 4
    stream = zlib.compress(plain)
    container = b'HEAD' + stream + bytes(2048 - 4 - len(stream))
    wire = dict(representations(container))[layout]
    result = probe(wire, offsets=[4])
    assert any(x['representation']==layout and x['codec']=='zlib'
               and x['output_sha256']==sha(plain) and x['trailer_bytes']>0
               for x in result['complete_streams'])


def test_no_alignment_truncation_or_unbounded_output():
    assert 'swap16' not in dict(representations(b'odd'))
    result = probe(zlib.compress(b'A' * 100000), offsets=[0], output_limit=1024)
    assert not any(x['codec']=='zlib' for x in result['complete_streams'])


def test_fixed_container_does_not_exclude_variable_compression():
    from scio_offline.transform_class import size_invariance
    a = zlib.compress(b'A' * 1000)
    b = zlib.compress(bytes(range(256)) * 4)
    assert len(a) != len(b)
    report = size_invariance({'sample':[a.ljust(1792,b'\0'), b.ljust(1792,b'\0')]})
    assert not report['length_ever_depends_on_content']
    assert 'Padding' in report['implication']
    assert 'does not establish a fixed-rate codec' in report['implication']
