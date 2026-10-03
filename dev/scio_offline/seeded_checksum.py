"""Invert selected non-cryptographic checksums to test unknown fixed seeds."""
MASK=(1<<32)-1


def rotl(x,n): return ((x<<n)|(x>>(32-n)))&MASK


def undo_xor_right(x,n):
    result=x
    for shift in range(n,32,n): result ^= x>>shift
    return result


def mix_word(k):
    return (rotl(k*0xcc9e2d51&MASK,15)*0x1b873593)&MASK


def murmur3(data,seed):
    h=seed
    for i in range(0,len(data)-len(data)%4,4):
        h^=mix_word(int.from_bytes(data[i:i+4],'little'))
        h=(rotl(h,13)*5+0xe6546b64)&MASK
    if len(data)%4: h^=mix_word(int.from_bytes(data[len(data)//4*4:],'little'))
    h^=len(data); h^=h>>16; h=h*0x85ebca6b&MASK; h^=h>>13; h=h*0xc2b2ae35&MASK; h^=h>>16
    return h


def recover_seed(data,output,algorithm):
    if algorithm=='murmur3':
        h=undo_xor_right(output,16)*pow(0xc2b2ae35,-1,1<<32)&MASK
        h=undo_xor_right(h,13)*pow(0x85ebca6b,-1,1<<32)&MASK
        h=undo_xor_right(h,16)^len(data)
        if len(data)%4: h^=mix_word(int.from_bytes(data[len(data)//4*4:],'little'))
        for i in reversed(range(0,len(data)-len(data)%4,4)):
            h=rotl((h-0xe6546b64)*pow(5,-1,1<<32)&MASK,19)
            h^=mix_word(int.from_bytes(data[i:i+4],'little'))
        return h
    h=output; prime=33 if algorithm=='djb2' else 16777619; inverse=pow(prime,-1,1<<32)
    for byte in reversed(data):
        if algorithm=='fnv1a': h=((h*inverse)&MASK)^byte
        elif algorithm=='fnv1': h=((h^byte)*inverse)&MASK
        elif algorithm=='djb2': h=(h-byte)*inverse&MASK
        else: raise ValueError('unsupported checksum')
    return h
