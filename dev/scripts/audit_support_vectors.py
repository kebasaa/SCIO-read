"""Read-only audit of the vendor support CSV; no workbook is modified."""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import numpy as np


def main():
    p=argparse.ArgumentParser(); p.add_argument('--output',required=True,type=Path); a=p.parse_args()
    root=Path(__file__).resolve().parents[2]
    path=root/'01_rawdata/app_researcher_output/SCIO_scans_from_tech_support.csv'
    with path.open(newline='',encoding='utf-8-sig') as f: rows=list(csv.reader(f))
    headers=[h.strip() for h in rows[10]]; data=rows[12:]; result={}
    arrays={}
    for prefix in ('spectrum_','wr_raw_','sample_raw_'):
        columns=[i for i,h in enumerate(headers) if h.startswith(prefix)]
        axis=[float(headers[i][len(prefix):]) for i in columns]
        if axis!=list(range(740,1071)): raise ValueError('unexpected wavelength axis')
        arrays[prefix]=np.array([[float(row[i]) for i in columns] for row in data])
        sv=np.linalg.svd(arrays[prefix],compute_uv=False)
        result[prefix]={'points':len(columns),'source_columns_zero_based':columns,
                        'unique_vectors':len(np.unique(arrays[prefix],axis=0)),
                        'singular_values':sv.tolist(),'relative_singular_values':(sv/sv[0]).tolist()}
    error=np.abs(arrays['sample_raw_']/arrays['wr_raw_']-arrays['spectrum_'])
    report={'source':path.relative_to(root).as_posix(),'source_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
            'source_data_rows_one_based':[13,len(rows)],'records':len(data),
            'device_ids':sorted({row[headers.index('device_id')].strip() for row in data}),
            'domains':result,'ratio_max_absolute_error':float(error.max()),
            'limits':'Exported domains corroborate the ratio calculation. No matching opaque blobs are established for this other device. SVD is exploratory, not a pixel-count or calibration-table recovery.'}
    out=a.output.resolve()
    if not out.is_relative_to(root/'dev'):raise ValueError('output must be under dev')
    out.parent.mkdir(parents=True,exist_ok=True)
    with out.open('x',encoding='utf-8') as f: json.dump(report,f,indent=2,allow_nan=False)
    print('support vectors audited:',len(data),'records')


if __name__=='__main__':main()
