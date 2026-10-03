"""Read-only CSV/factor comparison, with no extrapolation, interpolation or fitting.

Use the bundled scientific Python runtime for this spreadsheet analysis.
"""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import numpy as np


def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    root=Path(__file__).resolve().parents[2];dev=root/'dev'
    output=a.output.resolve()
    if not output.is_relative_to(dev):raise ValueError('output must be below dev')
    source=root/'01_rawdata/calibration_plate_Polypen.csv'
    factor_path=dev/'analysis_output/recovery_20261003_followup/symmetry/self_response_factor.json'
    with source.open(newline='',encoding='utf-8-sig') as handle:rows=list(csv.reader(handle))
    if rows[0]!=['wavelength','reflectance']:raise ValueError('unexpected source columns')
    data=np.asarray([[float(v) for v in row] for row in rows[1:]])
    if data.shape[1]!=2 or not np.isfinite(data).all() or np.any(np.diff(data[:,0])<=0):raise ValueError('invalid or ambiguous wavelengths')
    factor=json.loads(factor_path.read_text());wave=np.asarray(factor['wavelength_nm'])
    common,i,j=np.intersect1d(data[:,0],wave,return_indices=True)
    results={}
    for name in ('factor','inverse_factor'):
        y=np.asarray(factor[name])[j];delta=data[i,1]-y
        results[name]={'max_absolute_difference':float(np.max(np.abs(delta))),'rmse':float(np.sqrt(np.mean(delta**2))),
            'equivalent_at_1e_minus_6':bool(np.allclose(data[i,1],y,atol=1e-6,rtol=1e-6))}
    report={'source':source.relative_to(root).as_posix(),'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
        'source_header_row':1,'source_data_rows':[2,len(rows)],'source_columns':{'wavelength':'A','reflectance':'B'},
        'source_wavelength_range':[float(data[0,0]),float(data[-1,0])],'source_points':len(data),
        'factor_source':factor_path.relative_to(root).as_posix(),'factor_sha256':hashlib.sha256(factor_path.read_bytes()).hexdigest(),
        'exact_shared_wavelengths_nm':common.tolist(),'shared_points':len(common),'comparisons':results,
        'limits':'Source CSV has no device/reference identity or measurement provenance beyond its filename and column labels. Only exact shared wavelengths compared; no interpolation, extrapolation, rescaling or workbook modification. Numerical differences do not exclude a physical association under unknown measurement conditions.'}
    output.parent.mkdir(parents=True,exist_ok=True)
    with output.open('x',encoding='utf-8') as handle:json.dump(report,handle,indent=2,allow_nan=False)
    print(json.dumps({'range':report['source_wavelength_range'],'shared_points':len(common),'comparisons':results}))


if __name__=='__main__':main()
