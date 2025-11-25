# backend/app/api/v1/admin_dlq.py
from fastapi import APIRouter, Depends, HTTPException, Query
from typing import List
from backend.app.repositories.webhook_dlq_repository import WebhookDLQRepository
from backend.app.schemas.base import ORMBase
from pydantic import BaseModel
from backend.app.services.auth_service import get_current_admin

router = APIRouter()


class WebhookDLQOut(BaseModel):
    id: int
    url: str
    payload: dict | str | None
    headers: dict | None
    error: str | None
    attempts: int
    processed: bool
    created_at: str | None


@router.get("/api/v1/admin/dlq", response_model=List[WebhookDLQOut], dependencies=[Depends(get_current_admin)])
def list_dlq(limit: int = Query(50, ge=1, le=500), offset: int = Query(0, ge=0)):
    repo = WebhookDLQRepository()
    rows = repo.list(limit=limit, offset=offset, only_unprocessed=False)
    out = []
    for r in rows:
        out.append({
            "id": r.id,
            "url": r.url,
            "payload": r.payload,
            "headers": r.headers,
            "error": r.error,
            "attempts": r.attempts,
            "processed": r.processed,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        })
    return out


@router.post("/api/v1/admin/dlq/{entry_id}/requeue", dependencies=[Depends(get_current_admin)])
def requeue_dlq_entry(entry_id: int):
    """
    Requeue: attempts a single re-delivery synchronously (quick attempt).
    On success => marks processed. On failure => increments attempts and returns 502.
    Admins can use this to quickly repush selected entries.
    """
    repo = WebhookDLQRepository()
    entry = repo.get(entry_id)
    if not entry:
        raise HTTPException(status_code=404, detail="dlq_entry_not_found")

    # Attempt resend (lightweight)
    from backend.app.tasks.webhook_tasks import send_webhook_once
    try:
        code, text = send_webhook_once(entry.url, entry.payload or {}, headers=entry.headers or {})
        if 200 <= code < 300:
            repo.mark_processed(entry_id)
            return {"status": "ok", "requeued": True, "code": code}
        else:
            repo.increment_attempts(entry_id, error=f"manual_requeue_non2xx {code}: {text}")
            raise HTTPException(status_code=502, detail=f"delivery_failed {code}")
    except Exception as e:
        repo.increment_attempts(entry_id, error=str(e))
        raise HTTPException(status_code=500, detail=f"requeue_error: {str(e)}")


@router.delete("/api/v1/admin/dlq/{entry_id}", dependencies=[Depends(get_current_admin)])
def delete_dlq_entry(entry_id: int):
    repo = WebhookDLQRepository()
    ok = repo.delete(entry_id)
    if not ok:
        raise HTTPException(status_code=404, detail="dlq_entry_not_found")
    return {"status": "deleted", "id": entry_id}
