"""Run research tests with Python socket connections disabled; no production edits."""
import socket
import pytest
import _bootstrap


def denied(*args,**kwargs):
    raise RuntimeError('Network disabled for research verification')


if __name__=='__main__':
    socket.socket.connect=denied
    socket.socket.connect_ex=denied
    socket.create_connection=denied
    raise SystemExit(pytest.main(['dev/tests','-q','-o','cache_dir=dev/.pytest_cache','--basetemp=dev/.pytest_tmp_network_disabled']))
