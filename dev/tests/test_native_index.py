from scio_offline.native_index import functions, index_dump
from scio_offline.arm64_refs import scan_pool_loads, direct_calls
import struct


def test_raw_pool_load_patterns():
    add = 0x91000000 | (1 << 22) | (0x33 << 10) | (27 << 5) | 2
    load = 0xf9400000 | ((0x5a0//8) << 10) | (2 << 5) | 2
    direct = 0xf9400000 | ((0x100//8) << 10) | (27 << 5) | 0
    assert list(scan_pool_loads(struct.pack('<III', add, load, direct), 0x1000)) == [
        {'address':0x1004,'offset':0x335a0}, {'address':0x1008,'offset':0x100}]
    assert list(scan_pool_loads(struct.pack('<III', add, 0xd503201f, load))) == []


def test_direct_call_sign_extension():
    assert list(direct_calls(struct.pack('<II', 0x94000002, 0x97ffffff), 0x1000)) == [
        (0x1000, 0x1008), (0x1004, 0x1000)]


def test_function_boundaries():
    rows = list(functions('// ** addr: 0x10, size: 0x8\nbody\n// ** addr: 0x20, size: 0x4\nend'))
    assert [r['address'] for r in rows] == ['0x10', '0x20']
    assert rows[0]['size'] == 8
    assert 'end' not in rows[0]['lines']


def test_index_does_not_export_arbitrary_constants(tmp_path):
    (tmp_path / 'asm').mkdir()
    (tmp_path / 'pp.txt').write_text('[pp+0x10] String: "sample_dark"\n[pp+0x18] String: "secret-example"\n')
    (tmp_path / 'asm' / 'synthetic_native.dart').write_text(
        '// ** addr: 0x100, size: 0x20\n'
        '// [pp+0x10] "sample_dark"\n// [pp+0x18] "secret-example"\n'
        '// 0x108: bl #0x200\n')
    report = index_dump(tmp_path)
    assert report['functions'][0]['pool_refs'] == ['0x10']
    assert report['functions'][0]['calls'] == ['0x200']
    assert 'secret-example' not in str(report)
