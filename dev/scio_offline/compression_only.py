"""Compression-only probes: no cipher, key or smoothness assumption."""
import bz2
import lzma
import zlib
from .research import sha
from .search_v2 import image_candidates


FACTORIES={
    'deflate':lambda:zlib.decompressobj(-15),
    'zlib':lambda:zlib.decompressobj(15),
    'gzip':lambda:zlib.decompressobj(31),
    'bz2':bz2.BZ2Decompressor,
    'lzma_container':lambda:lzma.LZMADecompressor(memlimit=16*1024*1024),
}


def probe(data, byte_offsets=range(33), bit_offsets=range(8)):
    hits=[]
    for bit in bit_offsets:
        if bit:
            shifted=bytes(((data[i]<<bit)&255)|(data[i+1]>>(8-bit)) for i in range(len(data)-1))
        else: shifted=data
        for offset in byte_offsets:
            chunk=shifted[offset:]
            for name,factory in FACTORIES.items():
                decoder=factory(); output=bytearray(); consumed=0; failed=False
                # Bytewise feeding preserves partial output even when a later byte fails.
                for consumed,value in enumerate(chunk,1):
                    try: output.extend(decoder.decompress(bytes([value]),65536-len(output)))
                    except (ValueError,EOFError,OSError,zlib.error,lzma.LZMAError):
                        failed=True; break
                    if decoder.eof or len(output)>=65536: break
                if len(output)>=32:
                    hits.append({'codec':name,'byte_offset':offset,'bit_offset':bit,
                                 'complete_stream':bool(decoder.eof),'failed_after_output':failed,
                                 'input_consumed':consumed,'unused_input_bytes':len(chunk)-consumed,
                                 'output_bytes':len(output),'output_sha256':sha(output),
                                 'images':image_candidates(bytes(output))})
    return hits
