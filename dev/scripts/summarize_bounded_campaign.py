"""Read local checkpoint DB and publish a conservative, immutable assessment."""
import argparse
import json
import sqlite3
from pathlib import Path
import _bootstrap
from scio_offline import research as r


def signature(hit):
    return (hit['codec'],hit['offset'],hit.get('format'),tuple(hit.get('size',[])))


def assess(directory):
    manifest=json.loads((directory/'manifest.json').read_text())
    db=sqlite3.connect(f'file:{(directory / "results.sqlite").as_posix()}?mode=ro',uri=True)
    counts={}; leads=[]; candidates=[]; role_candidates=[]
    for index,stage,text in db.execute('SELECT job,stage,result FROM results ORDER BY job'):
        row=json.loads(text); counts.setdefault(stage,{})
        counts[stage][row['status']]=counts[stage].get(row['status'],0)+1
        if row['status']!='codec_lead': continue
        screens=row['screen']; confirmations=row['confirmation']
        sets=[{signature(h) for h in record['hits']} for record in screens+confirmations]
        common=set.intersection(*sets) if sets else set()
        # Current campaign: sample/dark, then two acquisitions with five roles.
        # Do not require a gradient to share the sample or dark's codec/layout.
        role_common={}
        for role,positions in {'sample':(0,2,7),'dark':(1,3,8)}.items():
            if len(sets)>max(positions):
                matching=set.intersection(*(sets[p] for p in positions))
                if matching: role_common[role]=[list(x) for x in sorted(matching)]
        lead={'job':index,'stage':stage,'screen_hit_counts':[len(x['hits']) for x in screens],
              'confirmation_hit_counts':[len(x['hits']) for x in confirmations],
              'common_codec_signatures':[list(x) for x in sorted(common)]}
        leads.append(lead)
        if role_common:
            role_candidates.append({'job':index,'stage':stage,'roles':role_common})
        if common:
            candidates.append(lead)
    db.close()
    completed=sum(sum(x.values()) for x in counts.values())
    return {'completed':completed,'total':len(manifest['configurations']), 'counts':counts,
            'codec_leads':leads,'cross_record_candidates':candidates,
            'same_role_cross_acquisition_candidates':role_candidates,
            'validated_intermediate':False,'validated_reflectance':False,'validated_domain_vectors':False,
            'limits':['Common codec signatures are only candidates; lengths, boundaries and meaning need independent support.',
                      'Negative screen applies to the two selected exploratory blobs, not every corpus record.',
                      'Only candidates reaching the frozen confirmation set can support an independent validation claim.',
                      'Controls are small empirical samples, not extreme-tail or familywise guarantees.']}


if __name__=='__main__':
    p=argparse.ArgumentParser(); p.add_argument('directory',type=Path); p.add_argument('--output',required=True)
    a=p.parse_args(); result=assess(a.directory); r.write_new(a.output,result)
    print(json.dumps({k:v for k,v in result.items() if k not in ('codec_leads','limits')},indent=2))
