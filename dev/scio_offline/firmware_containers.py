"""Bounded recognition of firmware JSON/XML envelopes; not firmware validation.

Never treats ScioFirmwareFiles version metadata as a payload. Does not execute
source, guess endpoints, or infer that a checksum prefix is a computed checksum.
"""
import base64
import binascii
import json
from xml.etree import ElementTree as ET

NAMES=frozenset(('ble','dsp_boot','dsp_dec','dsp_op','deadPixelsIndices','centers','bins','nPixelsPerBin'))


def decode_candidate(value):
    if not isinstance(value,str):return None
    compact=''.join(value.split())
    if not compact or len(compact)%4==1:return None
    try:
        raw=base64.b64decode(compact+'='*(-len(compact)%4),validate=True)
    except (ValueError,binascii.Error):return None
    return raw if len(raw)>4 else None


def inspect_text(text):
    """Return candidate bytes and count actual null update envelopes separately."""
    found=[]; null_updates=0; metadata=0
    def walk(obj,depth=0):
        nonlocal null_updates,metadata
        if depth>24:return
        if isinstance(obj,dict):
            if 'new_version' in obj and obj['new_version'] is None:null_updates+=1
            if 'ScioFirmwareFiles' in obj:metadata+=1
            for name,value in obj.items():
                if name in NAMES:
                    raw=decode_candidate(value)
                    if raw is not None:found.append((name,raw,'JSON named field'))
                if isinstance(value,(dict,list)):walk(value,depth+1)
        elif isinstance(obj,list):
            for value in obj:walk(value,depth+1)
    try:
        obj=json.loads(text);walk(obj)
    except (ValueError,RecursionError):
        # Log JSON may have a timestamp/Response prefix. Try one object per line.
        decoder=json.JSONDecoder()
        for line in text.splitlines():
            pos=line.find('{')
            if pos<0:continue
            try:obj,_=decoder.raw_decode(line[pos:]);walk(obj)
            except (ValueError,RecursionError):pass
    if '<' in text and ('<string' in text or '<map' in text):
        try:
            root=ET.fromstring(text)
            for item in root.iter('string'):
                name=item.get('name','')
                if name=='ScioFirmwareFiles':metadata+=1
                if name in NAMES:
                    raw=decode_candidate(item.text)
                    if raw is not None:found.append((name,raw,'XML named string'))
        except (ET.ParseError,ValueError):pass
    return {'candidates':found,'null_update_envelopes':null_updates,'version_metadata_fields':metadata}
