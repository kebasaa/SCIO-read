"""Content-based APK/member and vendor-code scan. Raw candidates remain private."""
import argparse
from collections import Counter
import io
import lzma
import re
import struct
import zipfile
import zlib
from pathlib import Path
import _bootstrap
from scio_offline import research as r
from scio_offline.resource_probe import encoded_runs,java_constants,decompress,formats
from scio_offline.firmware import parse_ldr

SIZES={7284,14600,32628,1714,96,140,1166,119233}


def main():
    p=argparse.ArgumentParser();p.add_argument('--apps',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    counts=Counter();seen=set();leads=[];archives=[];decoded=[]
    private=r.DEV/'private/embedded_resource_candidates';private.mkdir(parents=True,exist_ok=True)
    def inspect(data,origin,route,depth=0):
        digest=r.sha(data)
        counts['objects_seen']+=1
        if digest in seen:counts['duplicate_objects']+=1;return
        seen.add(digest);counts['unique_objects']+=1
        kind=formats(data)
        if kind:counts['format_'+kind]+=1
        reasons=[]
        # Bounded prefix envelopes; LDR plausibility only, never firmware identity.
        for offset in (0,4,8,16):
            if len(data)>=offset+16 and data[offset+3]==0xad:
                parsed=parse_ldr(data[offset:])
                if parsed['valid_ldr']:reasons.append({'kind':'LDR-structural-candidate','offset':offset,'blocks':parsed['n_blocks']})
        if not kind and (len(data) in SIZES or len(data)-4 in SIZES):
            reasons.append({'kind':'recorded-size-match-only'})
        if reasons:
            path=private/(digest+'.bin')
            if not path.exists():
                with path.open('xb') as f:f.write(data)
            leads.append({'source':origin,'route':route,'sha256':digest,'bytes':len(data),'reasons':reasons})
        if depth>=2:return
        for sig,codec in ((b'\x1f\x8b\x08','gzip'),(b'BZh','bzip2'),(b'\xfd7zXZ\0','xz'),(b'\x78\x9c','zlib'),(b'\x78\xda','zlib'),(b'\x78\x01','zlib')):
            for n,match in enumerate(re.finditer(re.escape(sig),data)):
                if n>=256:counts['codec_signature_cap_reached']+=1;break
                counts['codec_attempts']+=1
                try:out,used=decompress(data[match.start():],codec)
                except (ValueError,EOFError,OSError,lzma.LZMAError,zlib.error):
                    # Third-party codec errors deliberately do not export content.
                    counts['codec_rejected']+=1;continue
                if len(out)<64:continue
                decoded.append({'source':origin,'route':route,'codec':codec,'offset':match.start(),
                    'consumed':used,'decoded_bytes':len(out),'decoded_sha256':r.sha(out),'format':formats(out)})
                inspect(out,origin,route+'/'+codec+'@'+str(match.start()),depth+1)
        if route=='archive-member' and (kind in ('DEX','ELF') or '/assets/' in '/'+origin or '!assets/' in origin):
            for offset,encoding,out in encoded_runs(data):
                counts[encoding]+=1;inspect(out,origin,encoding+'@'+str(offset),depth+1)
    def archive(data,origin,depth=0):
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            for item in z.infolist():
                if item.is_dir():continue
                if item.file_size>128*1024*1024:counts['oversize_members_skipped']+=1;continue
                body=z.read(item);name=origin+'!'+item.filename
                if item.filename.endswith(('.apk','.zip')) and depth<3:
                    archive(body,name,depth+1)
                else:inspect(body,name,'archive-member')
    for path in sorted((a.apps/'apk').iterdir()):
        if path.suffix.lower() not in ('.apk','.xapk'):continue
        data=path.read_bytes();archives.append({'source':path.name,'sha256':r.sha(data)})
        archive(data,path.name)
        print('Audited archive',len(archives),flush=True)
    for path in sorted(a.apps.rglob('*.java')):
        relative=path.relative_to(a.apps).as_posix()
        if '/com/consumerphysics/' not in '/'+relative and '/_CHECK_consumerphysics/' not in '/'+relative:continue
        if path.stat().st_size>8*1024*1024:counts['oversize_java_skipped']+=1;continue
        counts['vendor_java_files']+=1
        for offset,encoding,data in java_constants(path.read_text(encoding='utf-8',errors='replace')):
            counts[encoding]+=1;inspect(data,relative,encoding+'@'+str(offset))
    r.write_new(a.output,{'counts':dict(counts),'archives':archives,'candidate_leads':leads,'decoded_streams':decoded,
        'limits':'Bounded gzip/zlib/bzip2/xz magic-guided decoding (8 MiB output, 256 signatures per kind/object, depth 2); contiguous Base64/hex strings in DEX/ELF/assets; JSON-compatible Java string literals and explicit literal numeric new byte/short/int arrays in vendor source. No arbitrary execution, XOR/key sweep, raw-deflate guessing, incremental array assignments, DEX fill-array-data interpretation, or general resource custom-container decoder. LDR structure and size matches are leads only. Raw strings/decoded data kept private; no firmware identity inferred.'})
    print('Unique objects',len(seen),'leads',len(leads),'decoded streams',len(decoded))


if __name__=='__main__':main()
