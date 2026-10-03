import numpy as np
from scio_offline import crc_recovery as c


def test_recovers_unknown_polynomial_and_constant_seed():
    rng=np.random.default_rng(741); polynomial=0x104C11DB7; blobs=[]
    for i in range(6):
        body=rng.bytes(128)
        checksum=c.remainder(int.from_bytes(body,'big')<<32,polynomial)^0x91827364
        blobs.append(bytes(4)+checksum.to_bytes(4,'big')+body)
    result=c.recover(blobs)
    assert any(h['gcd_polynomial_hex']==hex(polynomial) and h['all_confirm'] for h in result['hits'])


def test_random_headers_do_not_validate():
    rng=np.random.default_rng(138)
    assert not c.recover([rng.bytes(136) for _ in range(6)])['hits']


def test_murmur_seed_recovery():
    from scio_offline import seeded_checksum as s
    assert s.murmur3(b'foo',0)==0xf6a5c420
    for size in (0,1,3,4,5,128):
        data=bytes(range(size)); seed=0x93847561
        assert s.recover_seed(data,s.murmur3(data,seed),'murmur3')==seed


def test_fnv_and_djb_unknown_seeds():
    from scio_offline import seeded_checksum as s
    for algorithm in ('fnv1','fnv1a','djb2'):
        data=b'unknown seed fixture'; seed=0x81726354; h=seed
        for b in data:
            if algorithm=='fnv1': h=((h*16777619)&s.MASK)^b
            elif algorithm=='fnv1a': h=((h^b)*16777619)&s.MASK
            else:h=(h*33+b)&s.MASK
        assert s.recover_seed(data,h,algorithm)==seed
