from unittest.mock import patch, MagicMock
from backend.app.tasks.webhook_tasks import webhook_task
from backend.app.repositories.webhook_dlq_repository import WebhookDLQRepository

def test_webhook_task_success(monkeypatch):
    # mock HTTP success
    monkeypatch.setattr(
        "backend.app.tasks.webhook_tasks.send_webhook_once",
        lambda url, payload, headers=None: (200, "ok")
    )

    out = webhook_task.run(
        url="https://example.com",
        payload={"a": 1},
        headers=None
    )

    assert out is True


def test_webhook_task_failure_saved_to_dlq(monkeypatch):
    # 1) force webhook to always fail
    monkeypatch.setattr(
        "backend.app.tasks.webhook_tasks.send_webhook_once",
        lambda u, p, h=None: (500, "FAIL")
    )

    # 2) Fake DLQ repo.save
    saved = {}
    def fake_save(url, payload, headers, error, attempts):
        saved["url"] = url
        saved["attempts"] = attempts
        return True

    monkeypatch.setattr(WebhookDLQRepository, "save", fake_save)

    # 3) Allow only 1 retry so it hits DLQ fast
    task = webhook_task
    task.max_retries = 0

    out = task.run(
        url="https://fail.test",
        payload={"x": 1},
        headers=None
    )

    assert out is False
    assert saved["url"] == "https://fail.test"
