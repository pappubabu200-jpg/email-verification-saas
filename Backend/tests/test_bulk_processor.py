from unittest.mock import patch
from backend.app.services.bulk_processor import process_chunk

def test_process_chunk_success(monkeypatch):
    # Fake verification engine
    monkeypatch.setattr(
        "backend.app.services.bulk_processor.verify_email_sync",
        lambda email: {"status": "valid", "risk_score": 5, "details": {}}
    )

    # Fake backoff & slot
    monkeypatch.setattr("backend.app.services.bulk_processor.get_backoff_seconds", lambda d: 0)
    monkeypatch.setattr("backend.app.services.bulk_processor.acquire_slot", lambda d: True)
    monkeypatch.setattr("backend.app.services.bulk_processor.release_slot", lambda d: None)

    out_q = []
    class Q:
        def put(self, v): out_q.append(v)

    v, i, p = process_chunk(["a@test.com"], Q(), "/tmp/out")

    assert v == 1
    assert i == 0
    assert p == 1
    assert out_q[0][0] == "a@test.com"
