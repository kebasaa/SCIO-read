"""Framing-correct bounded searches; scores are leads, never decoded spectra."""
from __future__ import annotations

import hashlib
import io
import zlib
from collections import defaultdict
import numpy as np
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from . import decode, keyrecover, plaintext_oracles as po
from .research import sha


def image_candidates(data):
    """Decode bounded self-describing images at every matching marker offset.

    Headerless/custom JPEG and encrypted images need additional hypotheses;
    absence of these containers is not an exclusion of image compression.
    """
    from PIL import Image
    markers=(b'\xff\xd8\xff',b'\x89PNG\r\n\x1a\n',b'\xff\x4f\xff\x51',
             b'\x00\x00\x00\x0cjP',b'II*\x00',b'MM\x00*',b'GIF8',b'RIFF')
    offsets=set()
    for marker in markers:
        start=0
        while (offset:=data.find(marker,start))>=0:
            offsets.add(offset); start=offset+1
    hits=[]
    for offset in sorted(offsets):
        try:
            with Image.open(io.BytesIO(data[offset:])) as im:
                if im.width*im.height>65536: continue
                im.load()
                hits.append({'codec':'image','wbits':None,'format':im.format,'offset':offset,
                             'size':list(im.size),'mode':im.mode,'pixel_sha256':sha(im.tobytes())})
        except (OSError,ValueError,SyntaxError,Image.DecompressionBombError): pass
    return hits


def configurations(extended=False):
    yield ("ECB", "zero", 0)
    for mode in ("CBC", "CTR", "CFB", "OFB"):
        for iv in decode.IV_SCHEMES:
            yield (mode, iv, 0)
    if extended:
        for mode in ("CFB8", "CTR_LE"):
            for iv in ("zero", "header8_zero8", "zero8_header8", "first_block"):
                yield (mode, iv, 0)
        for mode in ("CBC", "CTR", "CFB", "OFB"):
            for iv in ("word_repeat", "word_zero", "word_be_zero"):
                yield (mode, iv, 0)
        for mode in ("ECB", "CBC", "CTR", "CFB", "OFB"):
            for iv in (("zero",) if mode == "ECB" else ("zero", "first_block")):
                yield (mode, iv, 16)


def transform(blob, key, config):
    if len(blob) < 24:
        raise ValueError("short blob")
    header, body = blob[:8], blob[8:]
    mode, scheme, trailer = config
    if trailer:
        body = body[:-trailer]
    if scheme in ("word_repeat", "word_zero", "word_be_zero"):
        word = header[4:8]
        iv = word*4 if scheme == "word_repeat" else (word[::-1] if scheme == "word_be_zero" else word)+bytes(12)
    else:
        iv = decode.make_iv(scheme, header, body)
    if scheme == "first_block":
        body = body[16:]
    if not body:
        raise ValueError("empty ciphertext")
    if mode == "CFB8":
        d = Cipher(algorithms.AES(key), modes.CFB8(iv)).decryptor()
        return d.update(body)+d.finalize()
    if mode == "CTR_LE":
        count = (len(body)+15)//16
        start = int.from_bytes(iv, "little")
        ctr = b"".join(((start+i) % (1<<128)).to_bytes(16,"little") for i in range(count))
        e = Cipher(algorithms.AES(key),modes.ECB()).encryptor()
        stream = e.update(ctr)+e.finalize()
        return np.bitwise_xor(np.frombuffer(body,dtype=np.uint8),np.frombuffer(stream[:len(body)],dtype=np.uint8)).tobytes()
    return decode.decrypt(body, key, mode, iv=iv, header=header)


def unpack_candidates(plain):
    """Bounded second layer. A codec hit requires an ended, nonempty stream."""
    hits=image_candidates(plain)
    for offset in (0,4,8,16):
        for wbits in (15,-15,31):
            try:
                d=zlib.decompressobj(wbits)
                out=d.decompress(plain[offset:],65536)
                if d.eof and len(out)>=32:
                    hits.append({"codec":"deflate", "wbits":wbits,"offset":offset,
                                 "bytes":len(out),"sha256":sha(out),"lane_score":po.dark_lane_score(out),
                                 "input_consumed":len(plain)-offset-len(d.unused_data),
                                 "unused_bytes":len(d.unused_data),'inner_images':image_candidates(out)})
            except zlib.error:
                pass
    return hits


def candidate_keys(device, extended=False):
    candidates=keyrecover.candidate_keys_from_device(device)
    if extended:
        tag=device.get("i2s_tag_config", "")
        # Explicit tag component/encoding gaps, not a password dictionary.
        seeds={"i2s.full":tag,"i2s.generation":tag.split(":")[0],
               "i2s.environment":tag.partition(":")[2],"i2s.date":tag.split("-")[0].split(":")[0]}
        for name,value in seeds.items():
            if not value: continue
            for encoding in ("ascii","utf-16le","utf-16be"):
                b=value.encode(encoding)
                for size in (16,24,32):
                    candidates[f"{name}.{encoding}.truncate_or_zeropad{size}"]=(b+bytes(size))[:size]
                for k,v in keyrecover._kdf_forms(b).items(): candidates[f"{name}.{encoding}.{k}"]=v
    by_key=defaultdict(list)
    for name,key in candidates.items(): by_key[key].append(name)
    return dict(by_key)


def search(blobs, keys, *, extended=False, random_count=128):
    """Screen every configuration; confirm independently on the remaining blobs."""
    configs=list(configurations(extended)); rows=[]; codec_hits=[]; attempted=0; failures=0
    for key,names in keys.items():
        for config in configs:
            attempted+=1
            try:
                plain=transform(blobs[0],key,config)
            except ValueError:
                failures+=1; continue
            score=po.dark_lane_score(plain)
            rows.append((score,key,config))
            hits=unpack_candidates(plain)
            if hits:
                confirmations=[]
                for blob in blobs[1:]:
                    try: next_hits=unpack_candidates(transform(blob,key,config))
                    except ValueError: next_hits=[]
                    confirmations.append(next_hits)
                consistent=[h for h in hits if confirmations and all(any(
                    n['codec']==h['codec'] and n['wbits']==h['wbits'] and n['offset']==h['offset'] and n.get('format')==h.get('format') for n in group)
                    for group in confirmations)]
                codec_hits.append({"candidate_sha256":sha(key),"config":config,"hits":hits,
                    "confirmation_records":len(confirmations),
                    "confirmation_records_with_any_hit":sum(bool(x) for x in confirmations),
                    "consistent_codec_parameters":consistent})
    rows.sort(key=lambda x:x[0],reverse=True)
    # Random controls use the identical configuration search, at all key widths.
    rng=np.random.default_rng(7319); null=[]
    for i in range(random_count):
        key=rng.bytes((16,24,32)[i%3]); best=-1
        for config in configs:
            try: best=max(best,po.dark_lane_score(transform(blobs[0],key,config)))
            except ValueError: pass
        null.append(best)
    candidates=[]
    # Top 32 are reported irrespective of cutoff: weak heuristics cannot exclude a key.
    for score,key,config in rows[:32]:
        other=[po.dark_lane_score(transform(b,key,config)) for b in blobs[1:]]
        candidates.append({"labels":keys[key],"candidate_sha256":sha(key),"config":config,
            "screen_score":score,"confirmation_min":min(other) if other else None,
            "confirmation_median":float(np.median(other)) if other else None,
            "heuristic_lead":bool(other and min(other)>max(null))})
    return {"schema":"scio-corrected-key-search/2","unique_keys":len(keys),
        "configurations":configs,"attempted":attempted,"invalid_configurations":failures,
        "blob_sha256":[sha(b) for b in blobs],"key_manifest":[{"sha256":sha(k),"derivations":v} for k,v in keys.items()],
        "random_controls":{"count":random_count,"best_scores":null,"resolution":1/(random_count+1),
                           "familywise_control":False},"top_candidates":candidates,"codec_hits":codec_hits,
        "validated_decoder":False,"limits":"No lane-entropy miss excludes encryption, a key, "
        "or compressed plaintext. Codec hits and entropy leads require independent validation."}
