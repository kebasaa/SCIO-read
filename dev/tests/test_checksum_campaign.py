import copy
import gzip
import hashlib
import io
import json
import struct
import zlib
import bz2
import lzma

import pytest
from PIL import Image
from scio_offline import checksum_campaign as c
from checksum_reference import encrypt_block,cbc,cmac,hmac256


@pytest.fixture
def owner():
    profile=copy.deepcopy(c.fw.OWN)
    profile.update(dsp_id='e24da26b2304c2c0',aptina_field='328045ab1161f198')
    return profile


def entry(blob,group='group0',role='sample',index=0):
    return {'blob':blob,'group':group,'role':role,'source':f'synthetic{index}'}


def encrypted(data,key,header,embedded=False,trailer=False):
    iv=header+bytes(8);plain=data+bytes((-len(data))%16)
    return header+(iv if embedded else b'')+cbc(key,plain,iv)+(bytes(16) if trailer else b'')


def test_reference_known_answers():
    assert encrypt_block(bytes.fromhex('000102030405060708090a0b0c0d0e0f'),bytes.fromhex('00112233445566778899aabbccddeeff')).hex()=='69c4e0d86a7b0430d8cdb78070b4c55a'
    assert encrypt_block(bytes(range(32)),bytes.fromhex('00112233445566778899aabbccddeeff')).hex()=='8ea2b7ca516745bfeafc49904b496089'
    key=bytes.fromhex('2b7e151628aed2a6abf7158809cf4f3c')
    assert cmac(key,b'').hex()=='bb1d6929e95937287fa37d129b756746'
    assert cmac(key,bytes.fromhex('6bc1bee22e409f96e93d7e117393172a')).hex()=='070a16b46b4d4144f79bdd9dd04a287c'
    assert hmac256(bytes([11])*20,b'Hi There').hex()=='b0344c61d8db38535ca8afceaf0bf12b881dc200c9833da726e9376c2e32cff7'


@pytest.mark.parametrize('family',['boot_checksum','dec_checksum','boot_dec_checksums','boot_header','dec_header','four_checksums'])
def test_each_seed_family_actual_driver(owner,tmp_path,monkeypatch,family):
    keys,_=c.keys_for(owner)
    key=next(k for k,labels in keys.items() if family+'.u32le.md5' in labels)
    plain=struct.pack('<128H',*range(128));encoded=zlib.compress(plain)
    inputs=[entry(encrypted(encoded,key,struct.pack('<II',0,i+1)),str(i),index=i) for i in range(3)]
    monkeypatch.setattr(c.r,'DEV',tmp_path)
    groups={'owner':{'profile':owner,'decode':inputs,'integrity':inputs}}
    job=('owner','decode',key,('CBC','header8_zero8',0),'header')
    manifest={'test':family,'jobs':[family]}
    summary=c.run(tmp_path/'run',manifest,[job],groups)
    assert summary['complete']
    with gzip.open(tmp_path/'run/outcomes.json.gz','rt') as stream: result=json.load(stream)[0]['result']
    assert result['status']=='cross_acquisition_codec_lead'
    assert all(any(h.get('sha256')==c.r.sha(plain) for h in row['codec']['hits']) for row in result['outcomes'])
    recovered=list((tmp_path/'private').rglob('lead*.bin'))
    assert recovered and zlib.decompress(recovered[0].read_bytes())==plain


@pytest.mark.parametrize('pack',[zlib.compress,bz2.compress,lzma.compress])
@pytest.mark.parametrize('embedded,trailer',[(False,False),(True,False),(True,True)])
def test_compression_envelopes_exact_recovery(pack,embedded,trailer):
    key=bytes(range(16));plain=bytes(range(256))*2
    blob=encrypted(pack(plain),key,b'ABCDEFGH',embedded,trailer)
    config=('CBC','first_block' if embedded else 'header8_zero8',16 if trailer else 0)
    result,_=c.evaluate_decode(key,config,[entry(blob)])
    assert any(h.get('sha256')==c.r.sha(plain) for h in result['outcomes'][0]['codec']['hits'])
    assert c.evaluate_decode(bytes(16),config,[entry(blob)])[0]['status']=='no_codec_hit'


def test_packed_plaintext_exact_transform():
    key=bytes(range(32));plain=struct.pack('<128H',*range(128));header=b'12345678'
    blob=encrypted(plain,key,header)
    assert c.transform(blob,key,('CBC','header8_zero8',0))==plain


@pytest.mark.parametrize('image_format',['PNG','JPEG','JPEG2000','TIFF','GIF','WEBP'])
def test_image_inside_compression(image_format):
    image=Image.new('L',(16,16),43);buf=io.BytesIO();image.save(buf,format=image_format)
    with Image.open(io.BytesIO(buf.getvalue())) as decoded: expected=c.r.sha(decoded.tobytes())
    key=bytes(range(16));blob=encrypted(zlib.compress(buf.getvalue()),key,b'12345678')
    result,_=c.evaluate_decode(key,('CBC','header8_zero8',0),[entry(blob)])
    assert any(h.get('sha256')==expected for hit in result['outcomes'][0]['codec']['hits'] for h in hit.get('inner_images',[]))


@pytest.mark.parametrize('config',list(c.integrity_configs()))
def test_integrity_independent_fixture(config,owner):
    key=bytes(range(16));inputs=[]
    for i in range(10):
        body=bytes([i])*64;word0=struct.pack('<I',i);blob=word0+bytes(4)+body
        layout=c.messages(blob,owner['device_id'])[config[1]]
        raw=cmac(key,layout) if config[0]=='AES-CMAC' else hmac256(key,layout)
        part=raw[:4] if config[2]=='first' else raw[-4:]
        blob=word0+int.from_bytes(part,config[3]).to_bytes(4,'little')+body
        inputs.append(entry(blob,str(i%3),index=i))
    result=c.evaluate_integrity(key,config,inputs,owner['device_id'])
    assert result['status']=='integrity_candidate'
    assert c.evaluate_integrity(key,config,inputs[:1]*12,owner['device_id'])['status']=='integrity_lead'
    assert c.evaluate_integrity(bytes(16),config,inputs,owner['device_id'])['status']=='no_match'


def test_identity_dedup_cap_and_missing(owner):
    keys,missing=c.keys_for(owner);assert not missing
    duplicate=copy.deepcopy(owner)
    duplicate['file_headers']['dsp_boot'][3]=duplicate['file_headers']['dsp_dec'][3]=0
    assert any(len(labels)>1 for labels in c.keys_for(duplicate)[0].values())
    bad=copy.deepcopy(owner);bad['dsp_id']='5291a26b2304c2c0'
    with pytest.raises(ValueError,match='mixed'):c.keys_for(bad)
    del owner['dsp_id'];assert 'dsp_id' in c.keys_for(owner)[1]
    assert c.check_cap([keys,keys,c.delta_keys()])<4096
    with pytest.raises(ValueError,match='limit'):c.check_cap([{i.to_bytes(16,'big'):[] for i in range(4097)}])


def test_boundaries_missing_codec_and_direct_controls(monkeypatch):
    with pytest.raises(ValueError):c.transform(bytes(25),bytes(16),('CBC','zero',0))
    with pytest.raises(ValueError):c.transform(bytes(24),bytes(16),('CBC','first_block',16))
    result=c.codecs.codecs(zlib.compress(b'x'*100)+b'junk')
    assert any(h.get('trailing')==4 and not h['trailing_zero'] for h in result['hits'])
    assert not c.codecs.codecs(zlib.compress(b'abc'))['hits']
    assert not c.codecs.codecs(zlib.compress(b'x'*100)[:-2])['hits']
    assert c.codecs.codecs(zlib.compress(b'x'*(c.codecs.LIMIT+1)))['codec_outcomes']['zlib:limit']>=1
    result,_=c.evaluate_decode(None,None,[entry(bytes(8)+zlib.compress(b'x'*100))])
    assert result['status']=='codec_lead'
    def absent(data):raise ImportError('synthetic unavailable image codec')
    monkeypatch.setattr(c,'codec_checks',absent)
    result,_=c.evaluate_decode(None,None,[entry(bytes(8)+b'x'*64)])
    assert result['outcomes'][0]['error']=='ImportError'


def test_resume_and_containment(owner,tmp_path,monkeypatch):
    monkeypatch.setattr(c.r,'DEV',tmp_path)
    entries=[entry(bytes(8)+bytes(range(64)))]
    groups={'test':{'profile':owner,'decode':entries,'integrity':entries}}
    jobs=[('test','direct',None,None,'compression-only'),('test','integrity',bytes(16),next(c.integrity_configs()),'header')]
    manifest={'test':'resume'}
    assert c.run(tmp_path/'run',manifest,jobs,groups,max_jobs=1)['completed']==1
    assert c.run(tmp_path/'run',manifest,jobs,groups)['completed']==2
    with pytest.raises(ValueError,match='manifest mismatch'):c.run(tmp_path/'run',{'test':'changed'},jobs,groups)
    with pytest.raises(ValueError):c.run(tmp_path.parent/'outside',manifest,jobs,groups)


@pytest.mark.parametrize('algorithm',['AES-CMAC','HMAC-SHA256'])
def test_integrity_through_actual_driver(algorithm,owner,tmp_path,monkeypatch):
    monkeypatch.setattr(c.r,'DEV',tmp_path)
    key=bytes(range(16));config=(algorithm,'body','first','little');inputs=[]
    for i in range(10):
        body=bytes([i])*64
        raw=cmac(key,body) if algorithm=='AES-CMAC' else hmac256(key,body)
        inputs.append(entry(bytes(4)+raw[:4]+body,str(i%3),index=i))
    groups={'test':{'profile':owner,'integrity':inputs,'decode':inputs}}
    result=c.run(tmp_path/'run',{'test':algorithm},[('test','integrity',key,config,'header')],groups)
    assert result['outcomes'][0]['status']=='integrity_candidate'


def test_sample_confirmation_not_vetoed_by_dark():
    key=bytes(range(16));inputs=[]
    for i in range(3):
        plain=bytes([i])*512
        inputs.append(entry(encrypted(zlib.compress(plain),key,struct.pack('<II',0,i)),str(i),index=i))
        inputs.append(entry(bytes(8)+bytes(range(64)),str(i),'sample_dark',index=i))
    result,_=c.evaluate_decode(key,('CBC','header8_zero8',0),inputs)
    assert result['status']=='cross_acquisition_codec_lead'
    assert result['same_role_confirmation']['sample']['consistent_signatures']
    assert not result['same_role_confirmation']['sample_dark']['consistent_signatures']


def test_inspector_immutable_upgrade_and_comparison(tmp_path,monkeypatch):
    original=c.r.DEV
    # Read the real profile before restricting writes to this test's directory.
    profile=c.fw.load_profile(original/'profiles/contributor_fw138.json')
    monkeypatch.setattr(c.r,'DEV',tmp_path)
    monkeypatch.setattr(c.fw,'load_profile',lambda path:profile)
    a=tmp_path/'synthetic_a';b=tmp_path/'synthetic_b'
    a.write_bytes((123).to_bytes(4,'little')+b'A'*64)
    b.write_bytes((124).to_bytes(4,'little')+b'A'*32+b'B'*32)
    result=c.inspect_artifacts(tmp_path/'inspection',a,'dsp_dec','container',b)
    assert result['comparison']['differing_positions']==32
    assert not result['artifacts'][0]['header_comparisons']['owner_fw147']['matches_current_size']
    assert result['artifacts'][0]['checksum_algorithm_established'] is False
    assert list((tmp_path/'private').rglob('*_original.bin'))
    with pytest.raises(FileExistsError):c.inspect_artifacts(tmp_path/'inspection',a,'dsp_dec','container')


def test_missing_image_library_keeps_generic_decompression(monkeypatch):
    import builtins
    original=builtins.__import__
    def unavailable(name,*args,**kwargs):
        if name=='PIL':raise ImportError('synthetic missing Pillow')
        return original(name,*args,**kwargs)
    monkeypatch.setattr(builtins,'__import__',unavailable)
    result=c.codec_checks(zlib.compress(b'A'*128))
    assert any(hit.get('sha256')==c.r.sha(b'A'*128) for hit in result['hits'])
    assert result['codec_outcomes']['image:ImportError']>=1


def test_image_limit_and_explicit_failure_outcomes():
    image=Image.new('L',(257,256),1);buf=io.BytesIO();image.save(buf,format='PNG')
    result=c.codec_checks(buf.getvalue())
    assert result['codec_outcomes']['image:limit']>=1
    assert not any(hit['codec']=='image' for hit in result['hits'])
    broken=c.codec_checks(b'\x89PNG\r\n\x1a\n'+bytes(64))
    assert any(key.startswith('image:') for key in broken['codec_outcomes'])


def test_changed_manifest_cannot_resume_with_replaced_inputs(owner,tmp_path,monkeypatch):
    monkeypatch.setattr(c.r,'DEV',tmp_path)
    inputs=[entry(bytes(8)+b'A'*64)]
    groups={'test':{'profile':owner,'decode':inputs,'integrity':inputs}}
    jobs=[('test','direct',None,None,'compression-only')]
    manifest={'inputs':c.r.sha(inputs[0]['blob']),'evaluator':'fixed'}
    c.run(tmp_path/'run',manifest,jobs,groups)
    for modified in ({**manifest,'inputs':'changed'},{**manifest,'evaluator':'changed'}):
        with pytest.raises(ValueError,match='manifest mismatch'):c.run(tmp_path/'run',modified,jobs,groups)


def test_static_audit_records_hashes_without_absolute_paths(tmp_path,monkeypatch):
    monkeypatch.setattr(c.r,'DEV',tmp_path)
    source=tmp_path/'synthetic_apps/SCiOBLeService.java'
    source.parent.mkdir();source.write_text('performFileDownload(outboundBytes);\nperformReadFileHeader(id);\n')
    result=c.audit_apps(source.parent,tmp_path/'audit')
    assert result['files'][0]['source']=='SCiOBLeService.java'
    assert result['files'][0]['sha256']==c.r.sha(source.read_bytes())
    assert result['device_commands_sent']==0
