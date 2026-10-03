"""Synthetic tests through the actual search driver; no device or network."""
import socket
import zlib
import numpy as np
import pytest
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from scio_offline import decode, research, search_v2


KEY=bytes(range(16))


def encrypt(plain, header, scheme, trailer=0):
    iv=bytes(range(16)) if scheme=='first_block' else decode.make_iv(scheme,header,b'')
    e=Cipher(algorithms.AES(KEY),modes.CBC(iv)).encryptor()
    return header+(iv if scheme=='first_block' else b'')+e.update(plain)+e.finalize()+bytes(trailer)


@pytest.mark.parametrize('scheme,trailer',[('header8_zero8',0),('first_block',0),('zero',16)])
def test_actual_search_known_key(scheme,trailer):
    plain=np.arange(896,dtype='<u2').tobytes()
    blobs=[encrypt(plain,bytes([i])*8,scheme,trailer) for i in (1,2)]
    result=search_v2.search(blobs,{KEY:['known'],bytes(16):['wrong']},extended=True,random_count=4)
    assert result['attempted']==2*len(set(search_v2.configurations(True)))
    config=('CBC',scheme,trailer)
    assert search_v2.transform(blobs[0],KEY,config)==plain
    assert any(c['candidate_sha256']==research.sha(KEY) and c['heuristic_lead'] for c in result['top_candidates'])
    assert not result['validated_decoder']


def test_compressed_packed_and_trailer():
    values=np.arange(640)%4096
    packed=bytes(x for a,b in zip(values[::2],values[1::2]) for x in (int(a)&255,(int(a)>>8)|((int(b)&15)<<4),int(b)>>4))
    compressed=zlib.compress(packed)
    padded=compressed+bytes((-len(compressed))%16)
    blob=encrypt(padded,b'12345678','zero',16)
    result=search_v2.search([blob,blob],{KEY:['known']},extended=True,random_count=2)
    assert any(hit['candidate_sha256']==research.sha(KEY) and any(h['sha256']==research.sha(packed) for h in hit['hits']) for hit in result['codec_hits'])


def test_packed_pixels_without_compression():
    values=np.random.default_rng(21).integers(0,4096,640)
    packed=bytes(x for a,b in zip(values[::2],values[1::2]) for x in (int(a)&255,(int(a)>>8)|((int(b)&15)<<4),int(b)>>4))
    blob=encrypt(packed,b'abcdefgh','zero')
    result=search_v2.search([blob],{KEY:['packed-known']},random_count=2)
    assert result['attempted']==len(list(search_v2.configurations()))
    assert search_v2.transform(blob,KEY,('CBC','zero',0))==packed
    assert result['key_manifest'][0]['sha256']==research.sha(KEY)
    assert not result['validated_decoder']


def test_actual_search_decrypt_then_jpeg():
    import io
    from PIL import Image
    buf=io.BytesIO(); Image.fromarray(np.arange(1024,dtype=np.uint8).reshape(32,32)).save(buf,format='JPEG')
    image=buf.getvalue(); plain=b'WRAP'+image; plain+=bytes((-len(plain))%16)
    blobs=[encrypt(plain,bytes([i])*8,'header8_zero8') for i in (1,2)]
    result=search_v2.search(blobs,{KEY:['jpeg-known'],bytes(16):['wrong']},random_count=2)
    assert any(c['candidate_sha256']==research.sha(KEY) and any(h.get('format')=='JPEG' for h in c['consistent_codec_parameters']) for c in result['codec_hits'])
    assert not result['validated_decoder']


def test_compression_without_encryption():
    from scio_offline.compression_only import probe
    data=bytes(range(256))*4
    hits=probe(b'prefix!!'+zlib.compress(data)+b'trailer',byte_offsets=(0,8),bit_offsets=(0,))
    assert any(h['codec']=='zlib' and h['complete_stream'] and h['output_sha256']==research.sha(data) for h in hits)


def test_no_silent_truncation():
    with pytest.raises(ValueError): decode.decrypt(bytes(17),KEY,'CBC')
    with pytest.raises(ValueError): search_v2.transform(bytes(25),KEY,('CBC','zero',0))


def test_strict_validation_offline(monkeypatch):
    def deny(*args,**kwargs): raise AssertionError('network disabled')
    monkeypatch.setattr(socket.socket,'connect',deny)
    axis=list(range(740,1071)); values=np.linspace(.2,1,331).tolist()
    truth={'wavelength_nm':axis,'reflectance':values}
    good=research.DecodeResult(axis,values)
    assert research.numerical_check(good,truth)['passed']
    assert not research.numerical_check(research.DecodeResult(axis,(np.array(values)*2).tolist()),truth)['passed']
    assert not research.numerical_check(research.DecodeResult(axis,values[::-1]),truth)['passed']
    good.sample_domain=values
    assert not research.numerical_check(good,truth)['passed']


def test_output_confinement():
    with pytest.raises(ValueError): research.write_new(research.ROOT/'forbidden.json',{})


def test_firmware_structural_bounds():
    import struct
    from scio_offline import firmware
    header=struct.pack('<IIII',0xAD008000,0x1000,32,0)
    assert not firmware.parse_ldr(header+b'short')['valid_ldr']
    assert not firmware.parse_ldr(header+bytes(33))['valid_ldr']
    result=firmware.parse_ldr(header+bytes(32))
    assert result['valid_ldr'] and not result['checksum_verified']


def test_oracle_limits_and_role_coverage():
    import sys
    sys.path.insert(0,str(research.DEV/'scripts'))
    import oracle_v2
    jobs=oracle_v2.probes(research.contexts())
    assert len(jobs)<=60
    for role in research.contexts()[0]['blobs']:
        for region in ('status','word2','begin','middle','end'):
            assert any(j['name']==role+'_'+region for j in jobs)
    assert jobs[0]['name']=='control_initial' and jobs[-1]['name']=='control_final'


@pytest.mark.parametrize('status',[401,403,429,500,200])
def test_oracle_failed_control_stops(tmp_path,monkeypatch,status):
    import sys
    sys.path.insert(0,str(research.DEV/'scripts'))
    import oracle_v2
    monkeypatch.setattr(research,'DEV',tmp_path)
    monkeypatch.setattr(oracle_v2.credentials,'get_token',lambda **kw:'synthetic-token')
    monkeypatch.setattr(oracle_v2.time,'sleep',lambda _:None)
    sent=[]
    class Response:
        status_code=status
        def json(self): return {'error':'synthetic failure'}
    def post(*args,**kwargs): sent.append(kwargs); return Response()
    monkeypatch.setattr(oracle_v2.requests,'post',post)
    oracle_v2.run(tmp_path/'run',True)
    assert len(sent)==1
    assert (tmp_path/'run/halt.json').exists()
    assert 'synthetic-token' not in ''.join(p.read_text() for p in (tmp_path/'run').glob('*.json'))
