import numpy as np
import pytest
from scio_offline.response_models import affine_from_two,comparison


def test_affine_predicts_third_sample_without_refitting():
    x0=np.linspace(.2,1,331);x1=x0+1;x2=x0+2
    scale=np.linspace(.8,1.2,331);bias=np.linspace(-.1,.1,331)
    a,b=affine_from_two(x0,x1,scale*x0+bias,scale*x1+bias)
    assert comparison(scale*x2+bias,a*x2+b)['equivalent']


def test_nonlinearity_can_fit_two_but_fails_third():
    x0=np.ones(331);x1=x0*2;x2=x0*3
    a,b=affine_from_two(x0,x1,x0**2,x1**2)
    assert comparison(x0**2,a*x0+b)['equivalent']
    assert not comparison(x2**2,a*x2+b)['equivalent']


def test_reject_degenerate_fit():
    with pytest.raises(ValueError):affine_from_two(np.ones(331),np.ones(331),np.ones(331),np.ones(331))
