from backend.app.tasks.dlq_retry_task import dlq_retry_worker

def test_dlq_retry_worker(monkeypatch):
    # Fake DLQ entries
    class Entry:
        id = 1
        url = "http://test"
        payload = '{"a":1}'
        headers = None

    fake_list = [Entry()]

    # Fake repo.list_failed
    monkeypatch.setattr(
        "backend.app.tasks.dlq_retry_task.WebhookDLQRepository.list_failed",
        lambda self: fake_list
    )

    # Fake repo.mark_resolved
    marked = []
    monkeypatch.setattr(
        "backend.app.tasks.dlq_retry_task.WebhookDLQRepository.mark_resolved",
        lambda self, id: marked.append(id)
    )

    # Fake webhook_task.delay
    sent = []
    monkeypatch.setattr(
        "backend.app.tasks.dlq_retry_task.webhook_task",
        type("T", (), {"delay": lambda url, payload, headers: sent.append(url)})
    )

    out = dlq_retry_worker()

    assert out["retried"] == 1
    assert sent == ["http://test"]
    assert marked == [1]
