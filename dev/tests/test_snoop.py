import struct
import pytest
from scio_offline.snoop import extract


def snoop(packets):
    return b'btsnoop\0'+struct.pack('>II',1,1002)+b''.join(struct.pack('>IIIIQ',len(p),len(p),f,0,0)+p for f,p in packets)


def acl(body,pb=2):
    return b'\x02'+struct.pack('<HH',1|(pb<<12),len(body))+body


def att(value):
    data=b'\x1b\x25\x00'+value
    return struct.pack('<HH',len(data),4)+data


def test_scio_and_acl_fragmentation():
    first=att(b'\x01\xba\x81\x14\x00'+b'A'*15)
    packets=[(1,acl(first[:9])),(1,acl(first[9:],1)),(1,acl(att(b'\x02'+b'B'*5)))]
    result=extract(snoop(packets))
    assert result['messages'][0]['data']==b'A'*15+b'B'*5
    assert result['messages'][0]['command']==0x81
    assert result['counts']['incomplete_scio']==0


def test_reject_sequence_gap_and_lengths():
    result=extract(snoop([(1,acl(att(b'\x01\xba\x02\x14\x00'+b'A'*15))),
                         (1,acl(att(b'\x03'+b'B'*5)))]))
    assert not result['messages']
    assert result['counts']['scio_sequence_error']==1
    with pytest.raises(ValueError): extract(snoop([(1,acl(att(b'123')))])[:-1])


def test_unrelated_att_not_exported():
    assert extract(snoop([(1,acl(att(b'unrelated private data')))]))['messages']==[]
