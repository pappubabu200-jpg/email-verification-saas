# backend/app/tasks/bulk_tasks.py
import logging
from decimal import Decimal, InvalidOperation
from typing import Union, Optional

from celery.utils.log import get_task_logger

from backend.app.celery_app import celery_app
from backend.app.services.bulk_processor import process_bulk_job

logger = get_task_logger(__name__)
logger.setLevel(logging.INFO)

@celery_app.task(
    bind=True,
    name="backend.app.tasks.bulk_tasks.process_bulk_job_task",
    max_retries=3,
    default_retry_delay=30,   # seconds
    acks_late=True,
    time_limit=60*60*2,       # 2 hours per bulk job (tune as needed)
)
def process_bulk_job_task(self, job_id: str, estimated_cost: Union[str, float, int, None] = None):
    """
    Celery entrypoint for processing a bulk job.

    Args:
        job_id: str - unique job identifier as stored in DB (BulkJob.job_id)
        estimated_cost: Decimal/float/str - estimated cost reserved for the job (optional)
    """

    # Validate inputs
    if not job_id:
        logger.error("process_bulk_job_task called without job_id")
        return {"ok": False, "error": "missing_job_id"}

    # Convert estimated_cost to Decimal
    est = Decimal("0")
    if estimated_cost is not None:
        try:
            est = Decimal(str(estimated_cost))
        except (InvalidOperation, TypeError):
            logger.warning("Invalid estimated_cost %s for job %s - using 0", estimated_cost, job_id)
            est = Decimal("0")

    try:
        logger.info("Starting bulk job worker for job_id=%s estimated_cost=%s", job_id, est)
        # process_bulk_job is synchronous (designed to be called from worker)
        process_bulk_job(job_id, est)
        logger.info("Finished bulk job worker for job_id=%s", job_id)
        return {"ok": True, "job_id": job_id}
    except Exception as exc:
        logger.exception("process_bulk_job_task failed for job_id=%s: %s", job_id, exc)
        try:
            # retry with exponential backoff
            raise self.retry(exc=exc)
        except Exception as retry_exc:
            logger.debug("Retry raised: %s", retry_exc)
        return {"ok": False, "error": str(exc)}
