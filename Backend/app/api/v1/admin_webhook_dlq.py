# backend/app/api/v1/admin_webhook_dlq.py

from fastapi import APIRouter, HTTPException, Depends, Query
from typing import Optional
import json

from backend.app.repositories.webhook_dlq_repository import WebhookDLQRepository
from backend.app.tasks.webhook_tasks import webhook_task
from backend.app.api.dependencies.auth import get_current_admin

router = APIRouter(
    prefix="/admin/webhook-dlq",
    tags=["Admin Webhook DLQ"]
)

repo = WebhookDLQRepository()


# ----------------------------------------------------
# LIST FAILED ENTRIES (Paginated)
# ----------------------------------------------------
@router.get("/", summary="List failed webhook DLQ entries")
def list_failed_entries(
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    admin=Depends(get_current_admin)
):
    rows = repo.list(limit=limit, offset=offset, only_unprocessed=True)
    return {
        "count": len(rows),
        "results": [
            {
                "id": r.id,
                "url": r.url,
                "payload": r.payload,
                "headers": r.headers,
                "error": r.error,
                "attempts": r.attempts,
                "created_at": r.created_at,
            }
            for r in rows
        ]
    }


# ----------------------------------------------------
# REQUEUE ONE ENTRY
# ----------------------------------------------------
@router.post("/requeue/{entry_id}", summary="Retry a specific DLQ entry")
def requeue_entry(entry_id: int, admin=Depends(get_current_admin)):
    entry = repo.get(entry_id)
    if not entry:
        raise HTTPException(404, "DLQ entry not found")

    payload = (
        json.loads(entry.payload)
        if isinstance(entry.payload, str)
        else entry.payload
    )
    headers = (
        json.loads(entry.headers)
        if entry.headers and isinstance(entry.headers, str)
        else entry.headers
    )

    webhook_task.delay(entry.url, payload, headers)
    repo.mark_processed(entry_id)

    return {"status": "requeued", "entry_id": entry_id}


# ----------------------------------------------------
# DELETE ENTRY
# ----------------------------------------------------
@router.delete("/{entry_id}", summary="Delete DLQ entry")
def delete_entry(entry_id: int, admin=Depends(get_current_admin)):
    ok = repo.delete(entry_id)
    if not ok:
        raise HTTPException(404, "DLQ entry not found")
    return {"status": "deleted", "entry_id": entry_id}


# ----------------------------------------------------
# RETRY ALL FAILED ENTRIES
# ----------------------------------------------------
@router.post("/requeue-all", summary="Retry ALL failed DLQ entries")
def requeue_all(admin=Depends(get_current_admin)):
    rows = repo.list(limit=5000, offset=0, only_unprocessed=True)

    count = 0
    for r in rows:
        payload = (
            json.loads(r.payload)
            if isinstance(r.payload, str)
            else r.payload
        )
        headers = (
            json.loads(r.headers)
            if r.headers and isinstance(r.headers, str)
            else r.headers
        )
        webhook_task.delay(r.url, payload, headers)
        repo.mark_processed(r.id)
        count += 1

    return {"status": "queued", "total_requeued": count}
