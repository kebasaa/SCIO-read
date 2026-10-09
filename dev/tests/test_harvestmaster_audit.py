import importlib
import struct
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'


def _audit(monkeypatch):
    monkeypatch.syspath_prepend(str(SCRIPTS))
    sys.modules.pop('audit_harvestmaster', None)
    return importlib.import_module('audit_harvestmaster')


def _pe(cli_rva):
    """Minimal PE32+ header with a chosen CLI data-directory RVA."""
    data = bytearray(0x200)
    data[:2] = b'MZ'
    struct.pack_into('<I', data, 0x3C, 0x80)
    data[0x80:0x84] = b'PE\0\0'
    struct.pack_into('<H', data, 0x80 + 24, 0x20B)
    struct.pack_into('<I', data, 0x80 + 24 + 112 + 14 * 8, cli_rva)
    return bytes(data)


def test_kind_separates_dotnet_from_native(monkeypatch):
    a = _audit(monkeypatch)
    assert a.kind(_pe(0x2000)) == '.net'
    assert a.kind(_pe(0)) == 'pe'
    assert a.kind(b'PK\x03\x04rest') == 'zip'
    assert a.kind(b'random') == 'other'


def test_vocab_counts_ascii_and_utf16(monkeypatch):
    a = _audit(monkeypatch)
    data = b'..ConsumerPhysics..' + 'scionir sample_dark'.encode('utf-16-le')
    hits = a.vocab_hits(data)
    assert hits['vendor'] == {'scio': 1, 'consumerphysics': 1, 'scionir': 1}  # 'scionir' contains 'scio'
    assert hits['payload'] == {'sample_dark': 1}


def test_audit_flags_sizes_and_checksums(monkeypatch, tmp_path):
    a = _audit(monkeypatch)
    (tmp_path / 'body.bin').write_bytes(b'\0' * 1792)
    (tmp_path / 'ck.bin').write_bytes(b'xx' + struct.pack('<I', 4151168) + b'yy')
    (tmp_path / 'plain.txt').write_bytes(b'nothing here')
    rows = {r['path']: r for r in a.audit([tmp_path], ['nothing'])}
    assert rows['body.bin']['known_size'] == 'sample/dark body'
    assert rows['ck.bin']['checksum_hits'] == {'dsp_op fw-147 checksum': [2]}
    assert 'nothing here' in rows['plain.txt']['snippets']['nothing'][0]
    assert [r['path'] for r in a.summarise(list(rows.values()))] == ['ck.bin']
