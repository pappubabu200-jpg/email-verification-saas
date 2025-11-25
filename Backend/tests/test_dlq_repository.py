from backend.app.repositories.webhook_dlq_repository import WebhookDLQRepository
from backend.app.models.webhook_dlq import WebhookDLQ

def test_dlq_repo_save(monkeypatch):
    saved_items = []

    # fake db session
    class FakeDB:
        def add(self, x): saved_items.append(x)
        def commit(self): pass
        def refresh(self, x): pass
        def close(self): pass

    monkeypatch.setattr(
        "backend.app.repositories.webhook_dlq_repository.SessionLocal",
        lambda: FakeDB()
    )

    repo = WebhookDLQRepository()
    repo.save("http://example.com", {"a":1}, None, "err", 1)

    assert len(saved_items) == 1
    assert isinstance(saved_items[0], WebhookDLQ)
