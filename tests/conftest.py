import pytest


@pytest.fixture(autouse=True)
def _no_real_geolocation(monkeypatch):
    """Tests never ask the machine's location service; capture stays offline and private."""
    from scio import location
    monkeypatch.setattr(location, "get_fix", lambda timeout=location.DEFAULT_TIMEOUT: (None, ["stubbed in tests"]))
