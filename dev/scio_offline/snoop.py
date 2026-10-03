"""Offline H4 btsnoop / ACL / ATT / SCIO reassembly, with strict lengths.

No live Bluetooth access. Export only SCIO-framed messages, not other traffic.
"""
import struct
from collections import Counter


def records(raw):
    if raw[:8]!=b'btsnoop\x00' or len(raw)<16:
        raise ValueError('not btsnoop')
    if struct.unpack('>II',raw[8:16])!=(1,1002):
        raise ValueError('requires version 1 H4 datalink 1002')
    offset=16; index=0
    while offset<len(raw):
        if offset+24>len(raw): raise ValueError('truncated record header')
        original,included,flags,drops,stamp=struct.unpack('>IIIIQ',raw[offset:offset+24])
        offset+=24
        if included>original or offset+included>len(raw): raise ValueError('truncated record')
        yield index,flags,raw[offset:offset+included]
        offset+=included; index+=1


def extract(raw):
    counts=Counter(); acl={}; frames={}; messages=[]; att_ops=Counter()
    for index,flags,packet in records(raw):
        counts['records']+=1
        if not packet or packet[0]!=2: continue
        counts['acl_packets']+=1
        if len(packet)<5: counts['short_acl']+=1; continue
        header,length=struct.unpack('<HH',packet[1:5]); body=packet[5:]
        if length!=len(body): counts['acl_length_error']+=1; continue
        connection=header&0xfff; pb=(header>>12)&3; direction=flags&1
        key=(connection,direction)
        if pb in (0,2):
            if key in acl: counts['interrupted_acl']+=1
            acl[key]=bytearray(body)
        elif pb==1 and key in acl: acl[key].extend(body)
        else: counts['orphan_acl']+=1; continue
        data=acl[key]
        if len(data)<4: continue
        n,cid=struct.unpack('<HH',data[:4])
        if len(data)<n+4: continue
        del acl[key]
        if len(data)!=n+4: counts['l2cap_length_error']+=1; continue
        if cid!=4 or not n: continue
        att=bytes(data[4:]); op=att[0]; att_ops[f'{op:02x}']+=1
        if op not in (0x12,0x52,0x1b,0x1d) or len(att)<4: continue
        handle=int.from_bytes(att[1:3],'little'); value=att[3:]
        stream=(connection,direction,handle)
        # A valid SCIO first packet establishes a candidate stream. Do not dump
        # unrelated ATT values (phone logs may contain other devices).
        if len(value)>=5 and value[:2]==b'\x01\xba':
            if stream in frames: counts['interrupted_scio']+=1
            frames[stream]={'command':value[2],'size':int.from_bytes(value[3:5],'little'),
                'data':bytearray(value[5:]),'sequence':2,'start_record':index}
        elif stream in frames:
            frame=frames[stream]
            if not value or value[0]!=frame['sequence']:
                counts['scio_sequence_error']+=1; del frames[stream]; continue
            frame['data'].extend(value[1:]); frame['sequence']=(frame['sequence']+1)&255
        else: continue
        frame=frames[stream]
        if len(frame['data'])>=frame['size']:
            del frames[stream]
            if len(frame['data'])!=frame['size']:
                counts['scio_length_error']+=1; continue
            messages.append({'command':frame['command'],'direction':'received' if direction else 'sent',
                'connection':connection,'attribute_handle':handle,'start_record':frame['start_record'],
                'end_record':index,'data':bytes(frame['data'])})
    counts['incomplete_acl']=len(acl); counts['incomplete_scio']=len(frames)
    return {'counts':dict(counts),'att_opcodes':dict(att_ops),'messages':messages}
