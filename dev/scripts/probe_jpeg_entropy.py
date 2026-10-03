"""Compression-only baseline JPEG entropy screening with random null controls."""
import argparse
import random
from pathlib import Path
import _bootstrap
from scio_offline import research as r
from scio_offline.jpeg_entropy import default_tables,probe


def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    blobs={r.sha(b):b for row in r.contexts() for b in row['blobs'].values()}
    tables=default_tables();results=[];total=0
    for digest,blob in blobs.items():
        n,hits=probe(blob,tables);total+=n
        if hits:results.append({'sha256':digest,'hits':hits})
    rng=random.Random(20261003);null=[];null_count=0
    for i in range(32):
        n,hits=probe(rng.randbytes(1800),tables);null_count+=n
        if hits:null.append({'index':i,'hits':hits})
    r.write_new(a.output,{'unique_blobs':len(blobs),'attempted_decodes':total,'hits':results,
        'random_controls':32,'random_attempted_decodes':null_count,'random_hits':null,
        'limits':'Only default luminance/chrominance baseline Huffman tables, bounded prefixes/trailers/alignment, with and without byte stuffing. No restart intervals, custom tables, arithmetic, lossless, progressive JPEG or non-JPEG codecs. No dimensions/quantization/pixel mapping recovered. Parse success alone is not validation.'})
    print('blobs',len(blobs),'attempts',total,'hit blobs',len(results),'null hit blobs',len(null))


if __name__=='__main__':main()
