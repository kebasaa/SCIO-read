"""Bounded keyless stream probes after reversible transport representations."""
import lzma
import zlib
from .compression_only import FACTORIES
from .research import sha

BIT_REVERSE = bytes(int(f'{x:08b}'[::-1], 2) for x in range(256))


def representations(data):
    yield 'identity', data
    for width in (2, 4):
        if len(data) % width == 0:
            yield f'swap{width * 8}', b''.join(data[i:i+width][::-1] for i in range(0,len(data),width))
    yield 'reverse_bits_per_byte', data.translate(BIT_REVERSE)


def probe(data, offsets=range(33), output_limit=65536):
    hits, tested = [], 0
    for representation, transformed in representations(data):
        for offset in offsets:
            if offset < 0 or offset >= len(transformed):
                continue
            chunk = transformed[offset:]
            for codec, factory in FACTORIES.items():
                tested += 1
                decoder = factory()
                try:
                    output = decoder.decompress(chunk, output_limit)
                except (ValueError, EOFError, OSError, lzma.LZMAError, zlib.error):
                    continue
                if not decoder.eof or not 32 <= len(output) < output_limit:
                    continue
                consumed = len(chunk) - len(decoder.unused_data)
                hits.append({'representation': representation, 'codec': codec,
                             'offset': offset, 'consumed_bytes': consumed,
                             'trailer_bytes': len(decoder.unused_data),
                             'output_bytes': len(output), 'output_sha256': sha(output)})
    return {'unique_configurations': tested, 'complete_streams': hits}
