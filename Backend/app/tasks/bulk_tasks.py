# backend/app/tasks/bulk_tasks.py
"""
Celery tasks for bulk job processing.

- process_bulk_job_task: main worker entry (delegates to services.bulk_processor.process_bulk_job)
- safe: loads job record, marks job status, captures exceptions and updates DB
- idempotent-ish: looks up job by job_id and will not re-run if already completed.
"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any, Optional

from backend.app.celery_app import celery_app
from backend.app.db import SessionLocal
from backend.app.models.bulk_job import BulkJob

from backend.app.services.bulk_processor import process_bulk_job

logger = logging.getLogger(__name__)

@celery_app.task(bind=True, name="backend.app.tasks.bulk_tasks.process_bulk_job_task", acks_late=True, autoretry_for=(Exception,), retry_backoff=True, retry_kwargs={"max_retries": 3})
def process_bulk_job_task(self, job_id: str, estimated_cost: float = 0.0) -> dict:
    """
    Celery task wrapper for processing bulk verification job.

    Parameters
    ----------
    job_id: str
        The unique job identifier matching BulkJob.job_id
    estimated_cost: float
        Credits reserved for the job (for refund math). Pass as float or decimal-compatible.

    Behavior
    - Checks DB job status and prevents double-processing when already 'completed' or 'running' (idempotency guard)
    - Calls process_bulk_job(job_id, Decimal(estimated_cost)) which is synchronous and safe for Celery
    - Updates job.status on unexpected failures (best-effort)
    """
    db = SessionLocal()
    try:
        job = db.query(BulkJob).filter(BulkJob.job_id == job_id).with_for_update(read=True).first()
        if not job:
            logger.error("Celery bulk task: job not found: %s", job_id)
            return {"ok": False, "reason": "job_not_found", "job_id": job_id}

        # Idempotency guard: if job already completed/processing, skip or re-run based on policy
        if job.status in ("running", "completed"):
            logger.info("Celery bulk task: job already in state %s: %s", job.status, job_id)
            return {"ok": True, "info": f"already_{job.status}", "job_id": job_id}

        # Mark job running (best-effort)
        try:
            job.status = "running"
            db.add(job)
            db.commit()
            db.refresh(job)
        except Exception as e:
            logger.debug("Failed to mark job running: %s", e)
            # continue anyway

        # Convert estimated_cost to Decimal
        try:
            est = Decimal(str(estimated_cost))
        except Exception:
            est = Decimal("0")

        # Call the heavy processor (synchronous)
        try:
            process_bulk_job(job_id, est)
            return {"ok": True, "job_id": job_id}
        except Exception as exc:
            logger.exception("process_bulk_job_task failed for %s: %s", job_id, exc)
            # Update job status to 'failed' in DB (best-effort)
            try:
                j2 = db.query(BulkJob).filter(BulkJob.job_id == job_id).first()
                if j2:
                    j2.status = "failed"
                    j2.error_message = str(exc)[:2000]
                    db.add(j2)
                    db.commit()
            except Exception:
                logger.exception("Failed to update job status after exception")
            # Let Celery handle retries if configured (this task is configured to autoretry)
            raise

    finally:
        try:
            db.close()
        except Exception:
            pass
