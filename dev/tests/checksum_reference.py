"""Scalar AES/CMAC fixture encryption, independent of production cipher APIs.

Validated by FIPS-197 and RFC 4493 known-answer vectors in the campaign tests.
Not used for decoding or for generating research hypotheses.
"""
import hashlib


def mul(a,b):
    result=0
    for _ in range(8):
        if b&1: result^=a
        a=((a<<1)^ (0x11b if a&128 else 0))&255;b>>=1
    return result


def sbox(value):
    inverse=0
    if value:
        inverse=1
        for _ in range(254): inverse=mul(inverse,value)
    result=inverse^0x63
    for shift in range(1,5): result^=((inverse<<shift)|(inverse>>(8-shift)))&255
    return result


SBOX=[sbox(i) for i in range(256)]


def encrypt_block(key,plain):
    nk=len(key)//4;nr=nk+6;words=[list(key[i:i+4]) for i in range(0,len(key),4)];rcon=1
    for index in range(nk,4*(nr+1)):
        temp=words[-1][:]
        if index%nk==0:
            temp=[SBOX[x] for x in temp[1:]+temp[:1]];temp[0]^=rcon;rcon=mul(rcon,2)
        elif nk>6 and index%nk==4: temp=[SBOX[x] for x in temp]
        words.append([x^y for x,y in zip(words[index-nk],temp)])
    state=list(plain)
    def add(round):
        return [state[i]^words[round*4+i//4][i%4] for i in range(16)]
    state=add(0)
    for round in range(1,nr+1):
        state=[SBOX[x] for x in state]
        state=[state[((col+row)%4)*4+row] for col in range(4) for row in range(4)]
        if round!=nr:
            mixed=[]
            for col in range(4):
                a,b,c,d=state[col*4:col*4+4]
                mixed.extend([mul(a,2)^mul(b,3)^c^d,a^mul(b,2)^mul(c,3)^d,
                              a^b^mul(c,2)^mul(d,3),mul(a,3)^b^c^mul(d,2)])
            state=mixed
        state=add(round)
    return bytes(state)


def cbc(key,plain,iv):
    result=b'';previous=iv
    assert len(plain)%16==0
    for offset in range(0,len(plain),16):
        previous=encrypt_block(key,bytes(x^y for x,y in zip(previous,plain[offset:offset+16])))
        result+=previous
    return result


def cmac(key,message):
    def double(value):
        n=int.from_bytes(value,'big');return (((n<<1)&((1<<128)-1))^(0x87 if n>>127 else 0)).to_bytes(16,'big')
    k1=double(encrypt_block(key,bytes(16)));k2=double(k1)
    if message and len(message)%16==0: prefix,last=message[:-16],bytes(x^y for x,y in zip(message[-16:],k1))
    else:
        cut=len(message)//16*16;prefix=message[:cut];tail=message[cut:]+b'\x80'
        last=bytes(x^y for x,y in zip(tail+bytes(16-len(tail)),k2))
    return cbc(key,prefix+last,bytes(16))[-16:]


def hmac256(key,message):
    if len(key)>64:key=hashlib.sha256(key).digest()
    key=key+bytes(64-len(key))
    inner=hashlib.sha256(bytes(x^0x36 for x in key)+message).digest()
    return hashlib.sha256(bytes(x^0x5c for x in key)+inner).digest()
