"""Bounded exploratory factor-shape and shared-dark/scalar-normalization checks.

Fitted diagnostic coefficients are NOT an accepted decoder or absolute values.
"""
import argparse
import json
from pathlib import Path
import numpy as np
import _bootstrap
from scio_offline import research as r
from scio_offline.response_models import comparison


def response(folder,name):
    for path in folder.glob('*_response.json'):
        data=json.loads(path.read_text())
        if data['name']==name:
            if data['status']!=200 or data['spectrum'] is None:raise ValueError('missing valid spectrum')
            return np.asarray(data['spectrum']),{'source':r.label(path),'sha256':r.sha(path.read_bytes())}
    raise KeyError(name)


def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    follow=r.DEV/'analysis_output/recovery_20261003_followup';old=r.DEV/'analysis_output/recovery_20261003/oracle_network'
    pairs=[((old,'control_initial'),(follow/'symmetry','dark_s0')),
           ((old,'sample_intact_substitution'),(follow/'symmetry','dark_s1')),
           ((follow/'dark_affine','new0_d0'),(follow/'dark_affine','new0_d1')),
           ((follow/'dark_affine','new1_d0'),(follow/'dark_affine','new1_d1'))]
    x=[];y=[];evidence=[]
    for left,right in pairs:
        first,fp=response(*left);second,sp=response(*right);x.append(first);y.append(second);evidence.extend([fp,sp])
    # Hypothesis: a_i*X_i - b_i*Y_i = common V(lambda). Eliminate V using pair 0.
    # Anchor a_0=1 to prevent the all-zero homogeneous solution.
    matrix=np.zeros((993,8))
    for i in range(1,4):
        section=slice((i-1)*331,i*331)
        matrix[section,0]=-x[0];matrix[section,1]=y[0]
        matrix[section,2*i]=x[i];matrix[section,2*i+1]=-y[i]
    training=np.tile(np.arange(331)%2==0,3)
    coefficients=np.r_[1.,np.linalg.lstsq(matrix[training,1:],-matrix[training,0],rcond=None)[0]]
    common=x[0]-coefficients[1]*y[0];checks={}
    for i in range(1,4):
        predicted=(coefficients[2*i]*x[i]-common)/coefficients[2*i+1]
        checks[f'sample_{i}']=comparison(y[i],predicted)
        checks[f'sample_{i}']['odd_band_max_absolute_error']=float(np.max(np.abs(y[i][1::2]-predicted[1::2])))
    factor_path=follow/'symmetry/self_response_factor.json';factor=json.loads(factor_path.read_text());wave=np.linspace(-1,1,331)
    shape={}
    for name in ('factor','inverse_factor'):
        values=np.asarray(factor[name]);shape[name]={'polynomial_max_errors':{},'finite_difference_near_zero_counts':{}}
        for degree in (1,2,3,4,6,8,12):
            fitted=np.polynomial.chebyshev.chebval(wave,np.polynomial.chebyshev.chebfit(wave,values,degree))
            shape[name]['polynomial_max_errors'][str(degree)]=float(np.max(np.abs(fitted-values)))
        for order in (1,2,3,4):shape[name]['finite_difference_near_zero_counts'][str(order)]=int((np.abs(np.diff(values,n=order))<1e-12).sum())
    report={'evidence':evidence,'factor_sha256':r.sha(factor_path.read_bytes()),'factor_shape':shape,
        'normalization_hypothesis':'a_i*X_i - b_i*Y_i = common V(lambda), with scalar a_i,b_i and a_0=1',
        'fit_coefficients':coefficients,'matrix_singular_values':np.linalg.svd(matrix,compute_uv=False),
        'fit_band_indices':'even zero-based indices','checks':checks,
        'limits':'Exploratory post-observation model test. All spectra have been inspected; alternating-band check is not a genuinely unseen confirmation set. Per-sample gain fitting here does not relax decoder validation or recover absolute sample/white values. Polynomial approximation is not the source of C.'}
    r.write_new(a.output,report)
    print(json.dumps({k:{a:b for a,b in v.items() if not a.startswith('per_band')} for k,v in checks.items()}))


if __name__=='__main__':main()
