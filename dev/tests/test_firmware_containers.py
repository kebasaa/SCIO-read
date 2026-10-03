import base64
import json
from scio_offline.firmware_containers import inspect_text,decode_candidate


def test_firmware_envelopes_and_checksum_preservation():
    raw=bytes(range(12));encoded=base64.b64encode(raw).decode()
    for text in (json.dumps({'new_version':{'dsp_op':encoded}}),
                 'Response: '+json.dumps({'new_version':{'dsp_op':encoded}}),
                 '<map><string name="dsp_op">'+encoded+'</string></map>'):
        result=inspect_text(text)
        assert result['candidates'][0][:2]==('dsp_op',raw)
    assert inspect_text("<map><string name='ble'>"+encoded+'</string></map>')['candidates'][0][:2]==('ble',raw)


def test_metadata_is_not_firmware():
    result=inspect_text(json.dumps({'new_version':None,'ScioFirmwareFiles':json.dumps([{'key':'5C','value':'93'}])}))
    assert result=={'candidates':[],'null_update_envelopes':1,'version_metadata_fields':1}
    result=inspect_text('<map><string name="ScioFirmwareFiles">W10=</string></map>')
    assert result['candidates']==[] and result['version_metadata_fields']==1


def test_narrow_candidates_and_malformed_input():
    assert decode_candidate('!!!!') is None
    assert decode_candidate('AAAAAA==') is None
    assert decode_candidate('A') is None
    assert inspect_text('{broken')['candidates']==[]
    assert inspect_text('{"password":"YWJjZGVmZ2g="}')['candidates']==[]
