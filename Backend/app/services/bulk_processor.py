import uuid
import logging
from typing import List, Optional
from backend.app.celery_app import celery_app

logger = logging.getLogger(__name__)

# Celery task name we will call (worker tasks should implement this)
VERIFY_TASK_NAME = "backend.app.workers.tasks.verify_email_task"

def submit_bulk_job(user_id: int, job_id: str, emails: List[str], meta: Optional[dict] = None) -> dict:
    """
    Enqueue verification tasks for a bulk job. This is a simple splitter that
    submits one celery task per email (you can later batch or chunk).
    """
    meta = meta or {}
    queued = 0
    for email in emails:
        try:
            # call by name to avoid circular imports
            celery_app.send_task(VERIFY_TASK_NAME, args=[email, {"user_id": user_id, "job_id": job_id}])
            queued += 1
        except Exception as e:
            logger.exception("Failed to enqueue verify task for %s: %s", email, e)
            continue
    return {"job_id": job_id, "queued": queued}
