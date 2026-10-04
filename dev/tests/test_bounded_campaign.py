import bz2
import io
import json
import lzma
import sqlite3
import zlib

import pytest
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from PIL import Image
from scio_offline import bounded_campaign as c


def encrypted(data, key, header=b'12345678', embedded=False, trailer=False):
    iv = header+bytes(8)
    padded = data + bytes((-len(data)) % 16)
    e = Cipher(algorithms.AES(key), modes.CBC(iv)).encryptor()
    body = e.update(padded)+e.finalize()
    return header+(iv if embedded else b'')+body+(bytes(16) if trailer else b'')


@pytest.mark.parametrize('field', c.EXTRA_FIELDS)
def test_new_identity_fields_through_actual_driver(field):
    value = '00112233445566778899aabbccddeeff'
    key = c.hashlib.md5(value.encode()).digest()
    keys = c.keys_for({'device_id':'test',field:value})
    assert key in keys
    plain = bytes(range(256))*4
    blobs=[encrypted(zlib.compress(plain), key, header=h) for h in (b'12345678',b'abcdefgh',b'87654321')]
    result=c.evaluate(key, ('AES','CBC','header8_zero8',0), blobs)
    assert result['status']=='codec_lead'
    for row in result['screen']+result['confirmation']:
        assert any(x.get('sha256')==c.research.sha(plain) for x in row['hits'])


@pytest.mark.parametrize('pack', [zlib.compress,bz2.compress,lzma.compress])
@pytest.mark.parametrize('embedded,trailer', [(False,False),(True,False),(True,True)])
def test_envelopes_and_compression(pack, embedded, trailer):
    plain=bytes(range(256))*4; key=bytes(range(16))
    blob=encrypted(pack(plain),key,embedded=embedded,trailer=trailer)
    config=('AES','CBC','first_block' if embedded else 'header8_zero8',16 if trailer else 0)
    result=c.evaluate(key,config,[blob]*3)
    assert any(h.get('sha256')==c.research.sha(plain) for h in result['screen'][0]['hits'])
    assert c.evaluate(bytes(16),config,[blob]*3)['status']=='no_codec_hit'


def test_image_inside_compression():
    im=Image.new('L',(16,16),42); out=io.BytesIO(); im.save(out,format='PNG')
    key=bytes(range(16)); blob=encrypted(zlib.compress(out.getvalue()),key)
    result=c.evaluate(key,('AES','CBC','header8_zero8',0),[blob]*3)
    assert any(h.get('inner_images') for h in result['screen'][0]['hits'])


@pytest.mark.parametrize('format', ['JPEG','JPEG2000','PNG','TIFF','GIF','WEBP'])
def test_supported_image_formats_recover_pixels(format):
    im=Image.new('RGB',(16,16),(42,42,42)); out=io.BytesIO(); im.save(out,format=format)
    encoded=out.getvalue()
    with Image.open(io.BytesIO(encoded)) as decoded:
        expected=c.research.sha(decoded.tobytes())
    key=bytes(range(16)); blob=encrypted(zlib.compress(encoded),key)
    result=c.evaluate(key,('AES','CBC','header8_zero8',0),[blob]*3)
    assert any(h.get('sha256')==expected for stream in result['screen'][0]['hits']
               for h in stream.get('inner_images',[]))


def test_optional_codec_absence_is_visible(monkeypatch):
    import importlib.util
    from pathlib import Path
    path=Path('dev/scripts/bounded_capabilities.py')
    spec=importlib.util.spec_from_file_location('bounded_capabilities',path)
    module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    Image.init(); monkeypatch.delitem(Image.OPEN,'WEBP')
    original=module.features.check
    monkeypatch.setattr(module.features,'check',lambda name: False if name=='webp' else original(name))
    report=module.capabilities()
    assert not report['image_plugins']['WEBP'] and not report['compiled_features']['webp']


def test_boundaries_and_limits():
    assert not c.codecs(zlib.compress(b'abc'))['hits']
    assert not c.codecs(zlib.compress(b'x'*100)[:-2])['hits']
    result=c.codecs(zlib.compress(b'x'*(c.LIMIT+1)))
    assert result['codec_outcomes']['zlib:limit'] >= 1
    result=c.codecs(zlib.compress(b'x'*100)+b'garbage')
    hit=next(h for h in result['hits'] if h['codec']=='zlib')
    assert hit['trailing']==7 and not hit['trailing_zero']
    with pytest.raises(ValueError): c.transform(b'a'*25, bytes(16), ('TEA','big','ECB',0))
    with pytest.raises(ValueError): c.transform(b'a'*25, bytes(16), ('AES','CBC','zero',0))


@pytest.mark.parametrize('name', ['ARC4','ChaCha20','TripleDES','Blowfish','Camellia'])
def test_cipher_adapters_independent_encrypt(name):
    key=bytes(range(32 if name=='ChaCha20' else 16)); plain=bytes(range(64))
    if name=='ChaCha20': alg=algorithms.ChaCha20(key,bytes(16)); mode=None; config=(name,'stream','zero',0)
    elif name=='ARC4': alg=algorithms.ARC4(key); mode=None; config=(name,'stream','none',0)
    else: alg=getattr(algorithms,name)(key); mode=modes.ECB(); config=(name,'ECB','zero',0)
    enc=Cipher(alg,mode).encryptor(); blob=bytes(8)+enc.update(plain)+enc.finalize()
    assert c.transform(blob,key,config)==plain


def test_tea_known_answer():
    # Standard zero-key/zero-plaintext 32-round TEA vector.
    blob=bytes(8)+bytes.fromhex('41ea3a0a94baa940')*2
    assert c.transform(blob,bytes(16),('TEA','big','ECB',0))==bytes(16)


def test_xtea_independent_scalar_encrypt():
    # Scalar reference independent of the vectorized decryption adapter.
    import struct
    key=bytes(range(16)); words=struct.unpack('>4I',key); output=b''
    plain=bytes(range(32))
    for offset in range(0,len(plain),8):
        a,b=struct.unpack('>2I',plain[offset:offset+8]); total=0
        for _ in range(32):
            a=(a+((((b<<4)^(b>>5))+b)^(total+words[total&3])))&0xffffffff
            total=(total+0x9e3779b9)&0xffffffff
            b=(b+((((a<<4)^(a>>5))+a)^(total+words[(total>>11)&3])))&0xffffffff
        output+=struct.pack('>2I',a,b)
    assert c.transform(bytes(8)+output,key,('XTEA','big','ECB',0))==plain


def test_packed_plaintext_and_no_codec_is_not_key_rejection():
    import struct
    plain=struct.pack('<128H',*range(128)); key=bytes(range(16))
    blob=encrypted(plain,key)
    assert c.transform(blob,key,('AES','CBC','header8_zero8',0))==plain
    result=c.evaluate(key,('AES','CBC','header8_zero8',0),[blob]*3)
    assert result['classification']=='bounded_negative'


def test_compressed_noise_recovers_without_repeatability_gate():
    rng=c.random.Random(447)
    key=bytes(range(16)); plains=[rng.randbytes(1600) for _ in range(3)]
    blobs=[encrypted(zlib.compress(p),key) for p in plains]
    result=c.evaluate(key,('AES','CBC','header8_zero8',0),blobs)
    for p,row in zip(plains,result['screen']+result['confirmation']):
        assert any(h.get('sha256')==c.research.sha(p) for h in row['hits'])


def test_identity_rejection_and_alias_provenance():
    with pytest.raises(ValueError): c.bind_identity({'device_id':'foreign'}, {}, 'local')
    keys=c.keys_for({'aptina_full':'00112233445566778899aabbccddeeff',
                     'aptinaId':'00112233445566778899aabbccddeeff'})
    labels=keys[bytes.fromhex('00112233445566778899aabbccddeeff')]
    assert any('aptina_full' in x for x in labels) and any('aptinaId' in x for x in labels)


def test_resume_and_output_guard(tmp_path, monkeypatch):
    monkeypatch.setattr(c.research,'DEV',tmp_path)
    blob=encrypted(zlib.compress(bytes(range(128))),bytes(16))
    jobs=[(bytes(16),('AES','CBC','header8_zero8',0),'test')]*2
    manifest={'input_hash':c.digest([c.research.sha(blob)])}
    directory=tmp_path/'campaign'
    assert c.run_jobs(directory,manifest,jobs,[blob]*3,max_jobs=1)==1
    assert c.run_jobs(directory,manifest,jobs,[blob]*3)==1
    assert c.run_jobs(directory,manifest,jobs,[blob]*3)==0
    with pytest.raises(ValueError): c.run_jobs(directory,{'input_hash':'changed'},jobs,[blob]*3)
    with pytest.raises(ValueError): c.output_dir(tmp_path.parent/'outside')


def test_resume_wrapper_normalizes_configuration_tuples(tmp_path, monkeypatch):
    import importlib.util
    from pathlib import Path
    spec=importlib.util.spec_from_file_location('resume_bounded',Path('dev/scripts/resume_bounded_campaign.py'))
    wrapper=importlib.util.module_from_spec(spec); spec.loader.exec_module(wrapper)
    monkeypatch.setattr(c.research,'DEV',tmp_path)
    blob=encrypted(zlib.compress(bytes(range(128))),bytes(16))
    config=('AES','CBC','header8_zero8',0)
    jobs=[(bytes(16),config,'test')]
    manifest={'input_hash':c.digest([c.research.sha(blob)]),'configurations':[config]}
    assert wrapper.run_jobs(tmp_path/'resume',manifest,jobs,[blob]*3)==1
    assert wrapper.run_jobs(tmp_path/'resume',manifest,jobs,[blob]*3)==0
    changed=dict(manifest,configurations=[('AES','ECB','zero',0)])
    with pytest.raises(ValueError): wrapper.run_jobs(tmp_path/'resume',changed,jobs,[blob]*3)
