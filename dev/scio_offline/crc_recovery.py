"""Recover unknown CRC polynomials from equal-length message differences.

For a fixed framing/length, CRC initial/final constants cancel under XOR.
Divisibility of difference codewords can therefore expose the generator without
guessing its polynomial or the device-specific seed. This does NOT test arbitrary
hashes, nonlinear checksums, or checksums of unobserved decompressed plaintext.
"""
from functools import reduce

BIT_REVERSE=bytes(int(f'{n:08b}'[::-1],2) for n in range(256))


def remainder(a,b):
    if not b: raise ValueError('zero polynomial')
    degree=b.bit_length()
    while a and a.bit_length()>=degree:
        a ^= b << (a.bit_length()-degree)
    return a


def gcd(a,b):
    while b: a,b=b,remainder(a,b)
    return a


def permute(data,kind):
    if kind=='identity': return data
    if kind=='bit_reverse': return data.translate(BIT_REVERSE)
    width={'swap16':2,'swap32':4}[kind]
    if len(data)%width: raise ValueError('unaligned permutation')
    return b''.join(data[i:i+width][::-1] for i in range(0,len(data),width))


def codeword(blob,start,end,body_order,field_order,placement):
    body=permute(blob[start:len(blob)-end if end else None],body_order)
    field=blob[4:8]
    if field_order&1: field=field[::-1]
    if field_order&2: field=field.translate(BIT_REVERSE)
    return int.from_bytes(body+field if placement=='append' else field+body,'big')


def recover(blobs):
    if len(blobs)<4 or len({len(b) for b in blobs})!=1:
        raise ValueError('requires four distinct equal-length records')
    if len(set(blobs))!=len(blobs): raise ValueError('deduplicate first')
    hits=[]; tested=0; failures=0
    configs=[(start,end,order,field,placement) for start in (8,12,16,24,32)
             for end in (0,4,8,16,32) for order in ('identity','bit_reverse','swap16','swap32')
             for field in range(4) for placement in ('append','prepend')]
    for config in configs:
        tested+=1
        try: words=[codeword(b,*config) for b in blobs[:4]]
        except ValueError: failures+=1; continue
        differences=[v^words[0] for v in words[1:]]
        polynomial=reduce(gcd,differences)
        # A CRC-32 generator of degree 32 would divide every difference.
        # Low-degree shared factors do not establish a CRC of width 32.
        if polynomial.bit_length()<33: continue
        confirmation=[remainder(codeword(b,*config)^words[0],polynomial)==0 for b in blobs[4:]]
        hits.append({'config':config,'gcd_polynomial_hex':hex(polynomial),
                     'degree':polynomial.bit_length()-1,'confirmation_count':len(confirmation),
                     'confirmation_passes':sum(confirmation),
                     'all_confirm':bool(confirmation) and all(confirmation)})
    return {'configurations':tested,'invalid_alignments':failures,'records':len(blobs),'hits':hits,
            'limits':'Fixed framing, equal-length affine CRC on observed body only. Does not exclude a CRC of hidden plaintext, a per-record variable seed, or other integrity mechanism.'}
