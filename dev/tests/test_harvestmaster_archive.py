"""Offline checks of the retained guide and bounded discovery ledger."""
import hashlib
import json
from pathlib import Path
import socket

ROOT = Path(__file__).resolve().parents[2]

def test_archive_budget():
    data = json.loads((ROOT / 'dev/analysis_output/harvestmaster_archive_20261009/REQUEST_LEDGER.json').read_text())
    assert sum(o['count'] for o in data['operations']) == 44
    assert data['prior_campaign_discovery_operations'] + sum(o['count'] for o in data['operations']) == 60
    assert sum(d['bytes'] for d in data['downloads']) < 2 * 1024**3
    assert data['new_executable_packages'] == 0

def test_guide_evidence_offline(monkeypatch):
    import pytest
    private = ROOT / 'dev/private/harvestmaster_archive_20261009/attempt_2'
    if not (private / 'h2_nir_guide.pdf').exists():
        pytest.skip('private vendor evidence not distributed')
    def denied(*args, **kwargs): raise RuntimeError('network blocked')
    monkeypatch.setattr(socket.socket, 'connect', denied)
    monkeypatch.setattr(socket, 'create_connection', denied)
    assert hashlib.sha256((private / 'h2_nir_guide.pdf').read_bytes()).hexdigest() == 'dedcb8f14cf36f77292f03fd95e86945fd00835c66ff1bde26f640cbf0200d59'
    inspection = json.loads((private / 'guide_inspection.json').read_text())
    assert len(inspection['pages']) == 32
    assert inspection['links'] == []
    for number in (16, 30):
        text = inspection['pages'][number - 1]['text'].lower()
        assert 'each sensor has its own activation link' in text
        assert 'license renewal' in text
