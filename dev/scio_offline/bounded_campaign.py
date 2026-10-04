"""Offline identity/codec coverage campaign. No network or device dependencies.

Reports describe bounded hypotheses, never identify a decoder by correlation.
"""
from __future__ import annotations

import bz2
import hashlib
import io
import itertools
import json
import lzma
import random
import sqlite3
import zlib
from pathlib import Path

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from . import keyrecover, search_v2, cipher_gap, research
from .embedded_cipher_hypothesis import decrypt_body

LIMIT = 1 << 20
STAGE = 'layered-v1'
EXTRA_FIELDS = ('aptina_full', 'aptinaId', 'aptina_upper', 'serial_prefix')


def digest(value):
    return research.sha(json.dumps(value, sort_keys=True, separators=(',', ':')).encode())


def keys_for(device):
    """Keep aliases separate until raw-byte deduplication, including pair labels."""
    out = search_v2.candidate_keys(device, True)
    for key, labels in cipher_gap.build_keys(device).items():
        out.setdefault(key, []).extend(labels)
    fields = {k: str(v) for k, v in device.items()
              if isinstance(v, (str, int)) and v != '' and k in (
                  *EXTRA_FIELDS, 'aptina_field', 'device_id', 'dsp_id', 'ble_id',
                  'serial_number', 'device_serial_fragment', 'address', 'i2s_tag_config')}
    def add(label, seed):
        for derivation, key in keyrecover._kdf_forms(seed).items():
            out.setdefault(key, []).append(label + '.' + derivation)
    for name in EXTRA_FIELDS:
        if name not in fields:
            continue
        value = fields[name]
        for label, text in [('ascii', value), ('lower', value.lower()), ('upper', value.upper())]:
            add(name + '.' + label, text.encode())
        try:
            raw = bytes.fromhex(value)
        except ValueError:
            continue
        for label, data in [('raw', raw), ('reverse', raw[::-1]),
                            ('word_swap', b''.join(raw[i:i+2][::-1] for i in range(0, len(raw), 2)))]:
            add(name + '.' + label, data)
    for a, b in itertools.combinations(sorted(fields), 2):
        if a not in EXTRA_FIELDS and b not in EXTRA_FIELDS:
            continue
        for sep in ('', ':', '-', '|'):
            for left, right in ((a, b), (b, a)):
                add(f'{left}+{right}.separator={sep!r}', (fields[left]+sep+fields[right]).encode())
    return {k: sorted(set(v)) for k, v in out.items()}


def bind_identity(device, observed, expected):
    if device.get('device_id') != expected:
        raise ValueError('identity mismatch')
    return {**device, **observed}


def configs(key):
    for c in search_v2.configurations(True):
        yield ('AES', *c)
    for cipher in cipher_gap.CIPHERS:
        if cipher in ('TEA', 'XTEA'):
            if len(key) == 16:
                for endian in ('big', 'little'):
                    for mode in ('ECB', 'CBC-zero'):
                        yield (cipher, endian, mode, 0)
        elif cipher == 'ARC4':
            yield (cipher, 'stream', 'none', 0)
        elif cipher == 'ChaCha20':
            if len(key) == 32:
                for iv in ('zero', 'header'):
                    yield (cipher, 'stream', iv, 0)
        elif cipher != 'TripleDES' or len(key) in (16, 24):
            yield (cipher, 'ECB', 'zero', 0)
            for mode in ('CBC', 'CFB', 'OFB'):
                for iv in ('zero', 'header', 'header_zero'):
                    yield (cipher, mode, iv, 0)


def transform(blob, key, config):
    cipher, mode, iv_name, trailer = config
    if len(blob) < 24:
        raise ValueError('short blob')
    if cipher == 'AES':
        return search_v2.transform(blob, key, (mode, iv_name, trailer))
    if trailer:
        raise ValueError('unsupported trailer')
    header, body = blob[:8], blob[8:]
    if cipher in ('TEA', 'XTEA'):
        if len(body) % 8:
            raise ValueError('unaligned TEA body')
        return decrypt_body(body, key, cipher, mode, iv_name)
    if cipher == 'ARC4':
        alg, m = algorithms.ARC4(key), None
    elif cipher == 'ChaCha20':
        alg, m = algorithms.ChaCha20(key, bytes(16) if iv_name == 'zero' else header*2), None
    else:
        alg = getattr(algorithms, cipher)(key)
        block = alg.block_size // 8
        if mode in ('ECB', 'CBC') and len(body) % block:
            raise ValueError('unaligned block body')
        iv = {'zero': bytes(block), 'header': (header*2)[:block],
              'header_zero': (header[:block//2]+bytes(block))[:block]}[iv_name]
        m = modes.ECB() if mode == 'ECB' else getattr(modes, mode)(iv)
    dec = Cipher(alg, m).decryptor()
    return dec.update(body)+dec.finalize()


def image_hits(data):
    """Marker-guided bounded image decode; image extent remains unverified."""
    from PIL import Image
    hits = []
    for marker in (b'\xff\xd8\xff', b'\x89PNG\r\n\x1a\n', b'\xff\x4f\xff\x51',
                   b'\x00\x00\x00\x0cjP', b'II*\x00', b'MM\x00*', b'GIF8', b'RIFF'):
        start = 0
        while (offset := data.find(marker, start)) >= 0:
            start = offset + 1
            try:
                with Image.open(io.BytesIO(data[offset:])) as im:
                    if im.width*im.height > 65536:
                        continue
                    im.load()
                    hits.append(dict(codec='image', offset=offset, format=im.format,
                                     size=list(im.size), sha256=research.sha(im.tobytes()),
                                     consumed=None, trailing=None, extent_verified=False))
            except (OSError, ValueError, SyntaxError, Image.DecompressionBombError):
                pass
    return hits


def codecs(data):
    hits = image_hits(data)
    failures = {}
    for offset in (0, 4, 8, 16):
        source = data[offset:]
        for name, factory in [('zlib', lambda: zlib.decompressobj(15)),
                              ('deflate', lambda: zlib.decompressobj(-15)),
                              ('gzip', lambda: zlib.decompressobj(31)),
                              ('bzip2', bz2.BZ2Decompressor), ('xz', lzma.LZMADecompressor)]:
            try:
                obj = factory()
                out = obj.decompress(source, LIMIT+1)
                if len(out) > LIMIT:
                    status = 'limit'
                elif not obj.eof:
                    status = 'incomplete'
                elif len(out) < 32:
                    status = 'short_parse'
                else:
                    trailing = len(obj.unused_data)
                    hits.append(dict(codec=name, offset=offset, bytes=len(out),
                                     sha256=research.sha(out), consumed=len(source)-trailing,
                                     trailing=trailing, trailing_zero=not any(obj.unused_data),
                                     inner_images=image_hits(out)))
                    status = 'hit'
            except (zlib.error, OSError, EOFError, ValueError, lzma.LZMAError) as exc:
                status = type(exc).__name__
            tag = name + ':' + status
            failures[tag] = failures.get(tag, 0)+1
    return {'hits': hits, 'codec_outcomes': failures}


def evaluate(key, config, blobs):
    """Screen sample AND dark without heuristic gates; confirm only codec leads."""
    rows = []
    for blob in blobs[:2]:
        try:
            rows.append(codecs(transform(blob, key, config)))
        except ValueError as exc:
            return {'status': 'invalid', 'error': str(exc)}
    lead = any(r['hits'] for r in rows)
    confirmations = []
    if lead:
        for blob in blobs[2:]:
            confirmations.append(codecs(transform(blob, key, config)))
    return {'status': 'codec_lead' if lead else 'no_codec_hit',
            'screen': rows, 'confirmation': confirmations,
            'classification': 'unvalidated_codec_parse' if lead else 'bounded_negative'}


def output_dir(path):
    path = Path(path).resolve()
    if not path.is_relative_to(research.DEV):
        raise ValueError('output must be below dev')
    path.mkdir(parents=True, exist_ok=True)
    return path


def run_jobs(directory, manifest, jobs, blobs, *, max_jobs=None):
    """Immutable per-configuration checkpoint, guarded by complete manifest hash."""
    directory = output_dir(directory)
    manifest_path = directory/'manifest.json'
    if manifest_path.exists():
        if json.loads(manifest_path.read_text()) != manifest:
            raise ValueError('resume manifest mismatch')
    else:
        research.write_new(manifest_path, manifest)
    db = sqlite3.connect(directory/'results.sqlite')
    db.execute('CREATE TABLE IF NOT EXISTS results (job INTEGER PRIMARY KEY, identity TEXT, stage TEXT, result TEXT)')
    done = 0
    for index, (key, config, stage) in enumerate(jobs):
        identity = digest([research.sha(key), config, stage, manifest['input_hash']])
        prior = db.execute('SELECT identity FROM results WHERE job=?', (index,)).fetchone()
        if prior:
            if prior[0] != identity:
                raise ValueError('checkpoint mismatch')
            continue
        inputs = blobs
        if stage == '5-random-body-controls':
            rng = random.Random(19731)
            inputs = [b[:8]+rng.randbytes(len(b)-8) for b in blobs]
        result = evaluate(key, config, inputs)
        db.execute('INSERT INTO results VALUES (?,?,?,?)', (index, identity, stage, json.dumps(result)))
        done += 1
        if done % 250 == 0:
            db.commit()
            print(f'completed {index+1}/{len(jobs)} ({stage})', flush=True)
        if max_jobs is not None and done >= max_jobs:
            break
    db.commit()
    db.close()
    return done
