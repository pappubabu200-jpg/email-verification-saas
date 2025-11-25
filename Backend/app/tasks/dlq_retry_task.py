from backend.app.celery_app import celery_app
from backend.app.repositories.webhook_dlq_repository import WebhookDLQRepository
from backend.app.tasks.webhook_tasks import webhook_task
import json

@celery_app.task(name="dlq.retry.worker")
def dlq_retry_worker():
    repo = WebhookDLQRepository()
    failed = repo.list_failed()

    for entry in failed:
        payload = json.loads(entry.payload)
        headers = json.loads(entry.headers) if entry.headers else None
        webhook_task.delay(entry.url, payload, headers)
        repo.mark_resolved(entry.id)

    return {"retried": len(failed)}
