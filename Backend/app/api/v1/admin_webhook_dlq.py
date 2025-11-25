from fastapi import APIRouter, Depends, HTTPException
from backend.app.repositories.webhook_dlq_repository import WebhookDLQRepository
from backend.app.tasks.webhook_tasks import webhook_task
import json

router = APIRouter(prefix="/admin/webhook-dlq", tags=["Admin Webhook DLQ"])

repo = WebhookDLQRepository()

@router.get("/")
def list_failed():
    return repo.list_failed()

@router.post("/requeue/{entry_id}")
def requeue(entry_id: int):
    rows = repo.list_failed()
    entry = next((r for r in rows if r.id == entry_id), None)
    if not entry:
        raise HTTPException(404, "DLQ entry not found")

    payload = json.loads(entry.payload)
    headers = json.loads(entry.headers) if entry.headers else None

    webhook_task.delay(entry.url, payload, headers)
    repo.mark_resolved(entry_id)

    return {"status": "requeued", "id": entry_id}
