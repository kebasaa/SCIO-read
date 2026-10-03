"""Compare named historical mock constants without exporting raw app strings."""
import argparse
from pathlib import Path
import _bootstrap
from audit_lab_fixtures import mock_constants
from scio_offline import research as r


def main():
    p=argparse.ArgumentParser();p.add_argument('--apps',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    current=r.DEV/'private/lab_1_3_12_java/sources/com/consumerphysics/researcher/mock/MockSamples.java'
    values=mock_constants(current.read_text())
    relative_paths=[
        'com.consumerphysics.researcher_2017-09-19_source_from_JADX/sources/com/consumerphysics/researcher/mock/MockSamples.java',
        'com.consumerphysics.researcher_2017-09-19_source_from_JADX/_CHECK_consumerphysics/researcher/mock/MockSamples.java',
        'TheLabDevToolkitforSCiO_1.3.12.144_Apkpure_source_from_JADX/sources/com/consumerphysics/researcher/mock/MockSamples.java']
    rows=[]
    for relative in relative_paths:
        path=a.apps/relative
        found=mock_constants(path.read_text())
        rows.append({'source':relative,'source_sha256':r.sha(path.read_bytes()),
            'constants':[{'name':name,'sha256':r.sha(data),'bytes':len(data),
                'same_named_lab_constant':data==values.get(name)} for name,data in found.items()]})
    r.write_new(a.output,{'sources':rows,'limits':'Comparison of six allowlisted named constants in three supplied source files. Directory date is provenance labeling, not independently verified build date. Not a whole-repository deduplication or paired-spectrum recovery.'})
    for row in rows:print(row['source'].split('/')[0],len(row['constants']),sum(x['same_named_lab_constant'] for x in row['constants']))


if __name__=='__main__':main()
