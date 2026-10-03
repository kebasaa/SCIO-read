"""Scan supplied text artifacts and top-level source ZIP text members read-only."""
import argparse
from collections import Counter
from pathlib import Path
import zipfile
import _bootstrap
from scio_offline import research as r
from scio_offline.firmware_containers import inspect_text,NAMES

SUFFIXES={'.xml','.json','.txt','.log'}
LIMIT=16*1024*1024


def main():
    p=argparse.ArgumentParser();p.add_argument('--apps',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    rows=[];counts=Counter();archives=[];seen={}
    def inspect(raw,origin):
        counts['text_files_or_members']+=1
        digest=r.sha(raw)
        if digest in seen:
            counts['duplicate_content']+=1
            if seen[digest]:rows.append({'source':origin,'sha256':digest,'same_content_as':seen[digest]})
            return
        counts['unique_text_contents']+=1
        # Parse only marker-bearing text; no unrelated text/credentials exported.
        if not any(s in raw for s in (b'new_version',b'ScioFirmwareFiles',*(name.encode() for name in NAMES))):
            seen[digest]=None;return
        result=inspect_text(raw.decode('utf-8-sig',errors='replace'))
        candidates=[]
        for name,data,kind in result.pop('candidates'):
            candidates.append({'name':name,'bytes_including_prefix':len(data),'sha256':r.sha(data),
                'prefix_u32le':int.from_bytes(data[:4],'little'),'body_sha256':r.sha(data[4:]),'container':kind})
        rows.append({'source':origin,'sha256':digest,'bytes':len(raw),'candidates':candidates,**result})
        seen[digest]=origin
        counts['marker_bearing_unique_texts']+=1
        counts['candidate_occurrences']+=len(candidates)
        counts['null_update_envelopes']+=result['null_update_envelopes']
    for root,label in ((r.ROOT/'01_rawdata','01_rawdata'),(r.ROOT/'02_processed_data','02_processed_data'),(a.apps,'<supplied-apps>')):
        for path in sorted(root.rglob('*')):
            if not path.is_file() or path.suffix.lower() not in SUFFIXES:continue
            if path.stat().st_size>LIMIT:counts['oversize_skipped']+=1;continue
            inspect(path.read_bytes(),label+'/'+path.relative_to(root).as_posix())
    for path in sorted(a.apps.glob('*.zip')):
        archive={'name':path.name,'sha256':r.sha(path.read_bytes()),'eligible_members':0}
        with zipfile.ZipFile(path) as z:
            for item in z.infolist():
                if item.is_dir() or Path(item.filename).suffix.lower() not in SUFFIXES:continue
                if item.file_size>LIMIT:counts['oversize_skipped']+=1;continue
                archive['eligible_members']+=1
                inspect(z.read(item),'archive:'+path.name+'!'+item.filename)
        archives.append(archive)
    r.write_new(a.output,{'counts':dict(counts),'archives':archives,'findings':rows,
        'limits':'JSON, line-prefixed JSON and named XML strings in listed text extensions, at most 16 MiB each. Top-level supplied source ZIPs included; no recursive archive traversal, Java arrays, custom binaries, multiline log-fragment reassembly, encrypted containers or exhaustive codec search. A candidate is not verified firmware; null new_version means that recorded response supplied no update, not that firmware never exists. Raw values are not exported.'})
    print(dict(counts))


if __name__=='__main__':main()
