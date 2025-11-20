
import uuid
import logging
from typing import List, Optional
from fastapi import HTTPException

from backend.app.celery_app import celery_app
from backend.app.services.credits_service import reserve_credits
from backend.app.services.credits_service import COST_PER_VERIFICATION, capture_reservation

logger = logging.getLogger(__name__)

# Celery task name (worker implements verify_email_task)
VERIFY_TASK_NAME = "backend.app.workers.tasks.verify_email_task"

def submit_bulk_job(user_id: int, job_id: str, emails: List[str], meta: Optional[dict] = None) -> dict:
    """
    Reserve credits for the bulk job, then enqueue tasks.
    If reservation fails (insufficient credits), raise HTTPException(402).
    """
    meta = meta or {}
    count = len(emails)
    total_cost = COST_PER_VERIFICATION * count

    # Reserve credits (throws HTTPException(402) if not enough)
    db = None
    try:
        from backend.app.db import SessionLocal
        db = SessionLocal()
        reservation = reserve_credits(db, user_id, total_cost, job_id=job_id, reference=job_id)
    except HTTPException:
        # bubble up to caller (API will return 402)
        raise
    except Exception as e:
        logger.exception("Failed to reserve credits: %s", e)
        raise HTTPException(status_code=500, detail="reserve_failed")
    finally:
        if db:
            db.close()

    queued = 0
    # enqueue tasks
    for email in emails:
        try:
            celery_app.send_task(VERIFY_TASK_NAME, args=[email, {"user_id": user_id, "job_id": job_id, "reservation_id": reservation.id}])
            queued += 1
        except Exception as e:
            logger.exception("Failed to enqueue verify task for %s: %s", email, e)
            continue

    # Return job info (reservation id can be used to capture when done)
    return {"job_id": job_id, "queued": queued, "reservation_id": reservation.id}
