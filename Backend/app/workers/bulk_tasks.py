from backend.app.celery_app import celery_app
from backend.app.services.bulk_processor import submit_bulk_job


@celery_app.task(name="backend.app.workers.bulk_tasks.enqueue_bulk")
def enqueue_bulk(user_id: int, job_id: str, emails: list):
    """
    External entry point if you want to enqueue bulk jobs from Celery.
    Not required for now but kept for scaling.
    """
    return submit_bulk_job(user_id, job_id, emails)
# backend/app/workers/bulk_tasks.py
from backend.app.celery_app import celery_app
from backend.app.services.bulk_processor import process_bulk_job
from decimal import Decimal
import logging

logger = logging.getLogger(__name__)

@celery_app.task(bind=True, max_retries=3)
def process_bulk_task(self, job_id: str, estimated_cost: float):
    """
    Celery wrapper. estimated_cost passed as float to avoid serialization issues.
    """
    try:
        process_bulk_job(job_id, Decimal(str(estimated_cost)))
        return {"ok": True}
    except Exception as e:
        logger.exception("process_bulk_task error: %s", e)
        raise self.retry(countdown=60)
