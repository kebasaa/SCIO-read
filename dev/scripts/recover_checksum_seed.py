import argparse
from pathlib import Path
import _bootstrap
from scio import session
from scio_offline import research as r,crc_recovery as c,seeded_checksum as s


def main():
    p=argparse.ArgumentParser(); p.add_argument('--output',required=True); a=p.parse_args(); groups={}
    for path in sorted(Path('01_rawdata/scans').glob('*.json')):
        rec=session.load_record(path); sample,white=session.record_blobs(rec)
        for role,b in {**sample,**white}.items(): groups.setdefault((rec['device']['device_id'],rec['device']['i2s_tag_config'],role),{})[r.sha(b)]=b
    rows=[]
    for identity,unique in groups.items():
        blobs=list(unique.values()); hits=[]; tested=0
        if len(blobs)<4: continue
        for start in (8,12,16,24,32):
            for end in (0,4,8,16,32):
                for order in ('identity','bit_reverse','swap16','swap32'):
                    for field_order in range(4):
                        for algorithm in ('murmur3','fnv1a','fnv1','djb2'):
                            tested+=1; seeds=[]
                            for b in blobs[:4]:
                                data=c.permute(b[start:-end if end else None],order); field=b[4:8]
                                if field_order&1: field=field[::-1]
                                if field_order&2: field=field.translate(c.BIT_REVERSE)
                                seeds.append(s.recover_seed(data,int.from_bytes(field,'big'),algorithm))
                                if len(set(seeds))>1: break
                            if len(set(seeds))==1: hits.append({'config':[start,end,order,field_order,algorithm],'seed':hex(seeds[0]),'screen_records':len(seeds)})
        rows.append({'identity':identity,'configurations':tested,'records':len(blobs),'blob_sha256':list(unique),'screen_hits':hits})
        print(identity[2],tested,'hits',len(hits),flush=True)
    r.write_new(a.output,{'groups':rows,'limits':'Tests fixed unknown seeds on observed bytes, not checksums of hidden decompressed data. Any screen hit still needs independent confirmation.'})


if __name__=='__main__':main()
