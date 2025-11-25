import pytest
from unittest.mock import MagicMock, patch

@pytest.fixture(autouse=True)
def no_network_calls(monkeypatch):
    """Block all external requests (safety)."""
    def blocked(*a, **kw):
        raise RuntimeError("NETWORK CALL BLOCKED IN TEST")

    monkeypatch.setattr("requests.post", blocked)
    monkeypatch.setattr("requests.get", blocked)
    monkeypatch.setattr("requests.put", blocked)
    monkeypatch.setattr("requests.delete", blocked)
    yield

@pytest.fixture
def mock_db_session():
    """Fake SQLAlchemy session object."""
    class FakeSession:
        def __init__(self):
            self.items = []
        def add(self, x): self.items.append(x)
        def commit(self): pass
        def close(self): pass
        def refresh(self, x): pass
    return FakeSession()
