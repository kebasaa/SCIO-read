import base64
import copy
import importlib
import json
from pathlib import Path

import pytest
from scio_offline import contributor_firmware as fw


@pytest.fixture
def profile():
    return fw.load_profile('dev/profiles/contributor_fw138.json')


class Clock:
    def __init__(self): self.now=0.;self.sleeps=[]
    def read(self): return self.now
    def sleep(self,seconds): self.sleeps.append(seconds);self.now+=seconds


class Response:
    def __init__(self,body,status=200,chunks=None):
        self.body=body;self.status_code=status;self.chunks=chunks
    def __enter__(self): return self
    def __exit__(self,*args): return False
    def iter_content(self,size): yield from self.chunks or [self.body]


def harness(monkeypatch,tmp_path,profile,responses,**kwargs):
    monkeypatch.setattr(fw.r,'DEV',tmp_path)
    clock=Clock(); calls=[];auth=[]
    def token():
        auth.append(clock.now);clock.now+=1
        return 'test-only-'+str(len(auth))
    def get(url,**options):
        calls.append({'url':url,'options':options,'time':clock.now})
        clock.now+=2
        item=responses[len(calls)-1]
        if isinstance(item,Exception): raise item
        return item
    result=fw.run(tmp_path/'run',profile,live=True,token_provider=token,getter=get,
                  monotonic=clock.read,sleeper=clock.sleep,**kwargs)
    return result,calls,auth,clock


def null(): return Response(b'{"new_version":null}')


def test_exact_four_keys_and_profile_validation(profile):
    jobs=fw.jobs_for(profile)
    assert [j['name'] for j in jobs]==['owner_control_initial','contributor_actual','contributor_zero','owner_control_final']
    assert all(set(j['versions'])==set(fw.KEYS) for j in jobs)
    assert jobs[1]['versions']['0x5C']=='0x8A'
    assert jobs[2]['profile']['i2s_tag_config']=='20150812:PRODUCTION'
    assert jobs[0]['profile']['ble_id']=='01665900004C99B4'
    bad=copy.deepcopy(profile);bad['ble_id']=fw.OWN['ble_id']
    with pytest.raises(ValueError): fw.validate_profile(bad)
    bad=copy.deepcopy(profile);bad['current_versions']['0x64']='0x01'
    with pytest.raises(ValueError): fw.validate_profile(bad)


def test_plan_only_without_auth_or_http(tmp_path,monkeypatch,profile):
    monkeypatch.setattr(fw.r,'DEV',tmp_path)
    def fail(): raise AssertionError('no auth expected')
    result=fw.run(tmp_path/'plan',profile,token_provider=fail)
    assert result['firmware_gets']==0
    assert (tmp_path/'plan'/'plan.json').exists()
    assert not (tmp_path/'private').exists()


def test_sequence_fresh_tokens_spacing_and_no_token_leaks(tmp_path,monkeypatch,profile):
    result,calls,auth,clock=harness(monkeypatch,tmp_path,profile,[null() for _ in range(4)])
    assert len(calls)==len(auth)==4
    assert [c['url'].split('/')[-2] for c in calls]==[fw.OWN['ble_id'],profile['ble_id'],profile['ble_id'],fw.OWN['ble_id']]
    assert [c['options']['params']['compression_version'] for c in calls]==['20150812-e:PRODUCTION','20150812:PRODUCTION','20150812:PRODUCTION','20150812-e:PRODUCTION']
    assert [c['options']['headers']['Authorization'] for c in calls]==['Bearer test-only-'+str(i) for i in range(1,5)]
    assert all(auth[i]-result['rows'][i-1]['completed_monotonic']>=20 for i in range(1,4))
    assert all(c['options']['allow_redirects'] is False for c in calls)
    for path in (tmp_path/'run').glob('*.json'):
        assert 'test-only-' not in path.read_text()
    assert len(list((tmp_path/'private').rglob('*_response.bin')))==4


def test_offer_stops_preserves_prefix_body_and_upgrade_mismatch(tmp_path,monkeypatch,profile):
    body=b'new firmware bytes'*20;container=(999).to_bytes(4,'little')+body
    raw=json.dumps({'new_version':{'dsp_op':base64.b64encode(container).decode()}}).encode()
    result,calls,*_=harness(monkeypatch,tmp_path,profile,[null(),Response(raw),null(),null()])
    assert len(calls)==2
    meta=result['artifacts'][0]
    assert not meta['header_comparisons']['contributor_fw138']['matches_current_size']
    assert not meta['header_comparisons']['owner_fw147']['matches_current_checksum_field']
    assert next((tmp_path/'private').rglob('dsp_op.bin')).read_bytes()==body
    assert next((tmp_path/'private').rglob('dsp_op.prefix')).read_bytes()==container[:4]
    assert next((tmp_path/'private').rglob('dsp_op.container')).read_bytes()==container
    assert next((tmp_path/'private').rglob('firmware_review.zip')).is_file()


@pytest.mark.parametrize('status',[301,302,401,403,429,500,503])
def test_http_failure_archived_and_halts(tmp_path,monkeypatch,profile,status):
    raw=b'{"error":"synthetic"}'
    result,calls,*_=harness(monkeypatch,tmp_path,profile,[Response(raw,status),null()])
    assert len(calls)==1 and result['rows'][0]['halt_reason']=='non-success HTTP status'
    assert next((tmp_path/'private').rglob('*_response.bin')).read_bytes()==raw


@pytest.mark.parametrize('raw',[b'not JSON',b'{}',b'[]',b'{"new_version":[]}',b'{"new_version":{"dsp_op":"AAAA"}}'])
def test_malformed_response_archived_and_halts(tmp_path,monkeypatch,profile,raw):
    result,calls,*_=harness(monkeypatch,tmp_path,profile,[Response(raw),null()])
    assert len(calls)==1 and result['rows'][0].get('halt_reason')
    assert next((tmp_path/'private').rglob('*_response.bin')).read_bytes()==raw


def test_null_and_empty_are_distinct(tmp_path,monkeypatch,profile):
    result,*_=harness(monkeypatch,tmp_path,profile,[null(),Response(b'{"new_version":{}}'),null(),null()])
    assert result['rows'][0]['offer_state']=='null'
    assert result['rows'][1]['offer_state']=='empty_map'


def test_unfamiliar_filename_quarantined(tmp_path,monkeypatch,profile):
    raw=b'{"new_version":{"../../escape":"YWJjZGVm"}}'
    result,calls,*_=harness(monkeypatch,tmp_path,profile,[Response(raw),null()])
    assert len(calls)==1 and result['rows'][0]['validation_errors']
    assert list((tmp_path/'private').rglob('quarantine_00.json'))
    assert not (tmp_path.parent/'escape').exists()


@pytest.mark.parametrize('value',['@@==','AQI','AAAA','AAAAAA==','AAAAAB==',0,None])
def test_strict_invalid_containers(value):
    with pytest.raises(ValueError): fw.strict_container(value)


def test_size_limit_preserves_capped_response(tmp_path,monkeypatch,profile):
    result,calls,*_=harness(monkeypatch,tmp_path,profile,[Response(b'',chunks=[b'a'*20,b'b'*20])],max_response=25)
    assert len(calls)==1 and result['rows'][0]['response_truncated']
    assert next((tmp_path/'private').rglob('*_response.bin')).read_bytes()==b'a'*20+b'b'*5


def test_transport_and_auth_failure_halt(tmp_path,monkeypatch,profile):
    result,calls,*_=harness(monkeypatch,tmp_path,profile,[TimeoutError('synthetic')])
    assert len(calls)==1 and result['rows'][0]['exception_type']=='TimeoutError'
    def auth(): raise ValueError('private-secret-do-not-record')
    result=fw.run(tmp_path/'auth',profile,live=True,token_provider=auth)
    assert result['firmware_gets']==0
    assert 'private-secret' not in json.dumps(result)


def test_immutable_output_and_outside_dev(tmp_path,monkeypatch,profile):
    monkeypatch.setattr(fw.r,'DEV',tmp_path)
    fw.run(tmp_path/'run',profile)
    with pytest.raises(FileExistsError): fw.run(tmp_path/'run',profile)
    with pytest.raises(ValueError): fw.run(tmp_path.parent/'outside',profile)
    path=tmp_path/'once.bin';fw.save_bytes(path,b'original')
    with pytest.raises(FileExistsError): fw.save_bytes(path,b'replacement')
    assert path.read_bytes()==b'original'


def test_checksum_difference_does_not_establish_key_region(profile):
    data=(12).to_bytes(4,'little')+b'abcdef'
    meta=fw.describe('dsp_dec',data,[fw.OWN,profile])
    assert meta['checksum_algorithm_established'] is False
    assert set(meta['header_comparisons'])=={'owner_fw147','contributor_fw138'}


def test_offline_inspection_checks_hash_without_network(tmp_path,monkeypatch,profile):
    result,*_=harness(monkeypatch,tmp_path,profile,[null() for _ in range(4)])
    script=Path('dev/scripts/contributor_firmware.py').resolve()
    monkeypatch.syspath_prepend(str(script.parent))
    spec=importlib.util.spec_from_file_location('contributor_firmware_cli',script)
    cli=importlib.util.module_from_spec(spec);spec.loader.exec_module(cli)
    def denied(*args,**kwargs): raise AssertionError('offline inspection must not authenticate or connect')
    monkeypatch.setattr(fw,'default_token',denied)
    monkeypatch.setattr(fw.requests,'get',denied)
    cli.inspect(tmp_path/'run',tmp_path/'review')
    reviewed=json.loads((tmp_path/'review'/'inspection.json').read_text())
    assert reviewed['network_requests']==0
    assert [row['offer_state'] for row in reviewed['rows']]==['null']*4
    source=fw.r.ROOT/result['rows'][0]['private_response_path']
    # Deliberate corruption of a synthetic fixture, never a real capture.
    source.write_bytes(b'changed synthetic archive')
    with pytest.raises(ValueError,match='hash mismatch'):
        cli.inspect(tmp_path/'run',tmp_path/'review_corrupt')


def test_partial_transport_response_is_preserved(tmp_path,monkeypatch,profile):
    class Broken(Response):
        def iter_content(self,size):
            yield b'partial'
            raise TimeoutError('synthetic stream timeout')
    result,calls,*_=harness(monkeypatch,tmp_path,profile,[Broken(b'')])
    assert len(calls)==1 and result['rows'][0]['exception_type']=='TimeoutError'
    assert next((tmp_path/'private').rglob('*_partial_response.bin')).read_bytes()==b'partial'
