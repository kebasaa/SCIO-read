"""Experimental response-level hypotheses, not opaque-blob decoders."""
import numpy as np


def vector(value):
    result=np.asarray(value,dtype=float)
    if result.shape!=(331,) or not np.isfinite(result).all():raise ValueError('requires 331 finite values')
    return result


def affine_from_two(x0,x1,y0,y1):
    x0,x1,y0,y1=map(vector,(x0,x1,y0,y1));delta=x1-x0
    if np.any(np.abs(delta)<1e-10):raise ValueError('unstable two-point affine denominator')
    slope=(y1-y0)/delta
    return slope,y0-slope*x0


def comparison(actual,expected):
    actual=vector(actual);expected=vector(expected);error=actual-expected
    return {'equivalent':bool(np.allclose(actual,expected,atol=1e-6,rtol=1e-6)),
        'failed_bands':int((~np.isclose(actual,expected,atol=1e-6,rtol=1e-6)).sum()),
        'max_absolute_error':float(np.max(np.abs(error))),'rmse':float(np.sqrt(np.mean(error**2))),
        'per_band_signed_error':error}
