import importlib
from types import SimpleNamespace
import numpy as np
from scio_offline import research


def test_historical_control_drift_stops_before_combinations(monkeypatch):
    monkeypatch.syspath_prepend(str(research.DEV/'scripts'))
    oracle=importlib.import_module('oracle_v2')
    saved={}; calls=[]
    monkeypatch.setattr(oracle.r,'write_new',lambda p,d:saved.update({p.name:d}))
    monkeypatch.setattr(oracle.credentials,'get_token',lambda **kwargs:'unit-test-token')
    monkeypatch.setattr(oracle.time,'sleep',lambda seconds:None)
    monkeypatch.setattr(oracle.cloud,'spectrum_from_response',lambda response:(np.arange(740,1071),np.ones(331)))
    def fake_post(*args,**kwargs):
        calls.append(1)
        return SimpleNamespace(status_code=200,json=lambda:{})
    monkeypatch.setattr(oracle.requests,'post',fake_post)
    oracle.run_jobs(research.DEV/'unused-test-output',[
        {'name':'control_initial','payload':{},'changes':{},'expected_spectrum':[0]*331},
        {'name':'compose_sw','payload':{},'changes':{}}],live=True)
    assert len(calls)==1
    assert saved['halt.json']['reason']=='historical control drift'
    assert len(saved['summary.json']['requests'])==1


def test_failed_probe_skips_dependent_job_but_runs_final_control(monkeypatch):
    monkeypatch.syspath_prepend(str(research.DEV/'scripts'))
    oracle=importlib.import_module('oracle_v2');saved={};calls=[]
    monkeypatch.setattr(oracle.r,'write_new',lambda p,d:saved.update({p.name:d}))
    monkeypatch.setattr(oracle.credentials,'get_token',lambda **kwargs:'unit-test-token')
    monkeypatch.setattr(oracle.time,'sleep',lambda seconds:None)
    monkeypatch.setattr(oracle.cloud,'spectrum_from_response',lambda response:(np.arange(740,1071),np.ones(331)))
    def fake_post(*args,**kwargs):
        calls.append(kwargs['json']['id'])
        return SimpleNamespace(status_code=422 if len(calls)==1 else 200,json=lambda:{})
    monkeypatch.setattr(oracle.requests,'post',fake_post)
    oracle.run_jobs(research.DEV/'unused-test-output',[
        {'name':'dark_s0','payload':{'id':0},'changes':{}},
        {'name':'dark_s1','payload':{'id':1},'changes':{},'requires_valid_spectrum':'dark_s0'},
        {'name':'control_final','payload':{'id':2},'changes':{},'expected_spectrum':[1]*331}],live=True)
    assert calls==[0,2]
    assert saved['01_skipped.json']['dependency']=='dark_s0'
    assert len(saved['summary.json']['requests'])==2
