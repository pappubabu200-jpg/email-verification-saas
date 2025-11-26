# backend/app/tasks/bulk_tasks.py
"""
Celery tasks for bulk job processing.
Now with webhook on completion (both success & failure).
"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any

from backend.app.celery_app import celery_app
from backend.app.db import SessionLocal
from backend.app.models.bulk_job import BulkJob

from backend.app.services.bulk_processor import process_bulk_job
from backend.app.services.webhook_service import trigger_webhook  # ← ADDED

logger = logging.getLogger(__name__)


@celery_app.task(
    bind=True,
    name="backend.app.tasks.bulk_tasks.process_bulk_job_task",
    acks_late=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_kwargs={"max_retries": 3}
)
def process_bulk_job_task(self, job_id: str, estimated_cost: float = 0.0) -> dict:
    db = SessionLocal()
    try:
        job = db.query(BulkJob).filter(BulkJob.job_id == job_id).with_for_update(read=True).first()
        if not job:
            logger.error("Celery bulk task: job not found: %s", job_id)
            return {"ok": False, "reason": "job_not_found", "job_id": job_id}

        # Idempotency guard
        if job.status in ("running", "completed"):
            logger.info("Celery bulk task: job already %s: %s", job.status, job_id)
            return {"ok": True, "info": f"already_{job.status}", "job_id": job_id}

        # Mark as running
        job.status = "running"
        db.add(job)
        db.commit()
        db.refresh(job)

        # Convert cost
        est = Decimal(str(estimated_cost)) if estimated_cost else Decimal("0")

        # Run the actual processing
        try:
            process_bulk_job(job_id, est)

            # Final job stats (re-fetch to get latest counters)
            db.refresh(job)
            final_stats = {
                "job_id": job.job_id,
                "status": job.status,
                "total": job.total or 0,
                "processed": job.processed or 0,
                "valid": job.valid or 0,
                "invalid": job.invalid or 0,
                "risky": getattr(job, "risky", 0) or 0,
                "unknown": getattr(job, "unknown", 0) or 0,
                "completed_at": job.updated_at.isoformat() if job.updated_at else None,
            }

            # FIRE WEBHOOK ON SUCCESS
            try:
                trigger_webhook.delay(  # .delay() because we're already in a Celery task
                    "bulk_job.finished",
                    final_stats,
                    team_id=job.team_id or job.user_id  # fallback if no team
                )
            except Exception as webhook_err:
                logger.warning("Failed to trigger bulk_job.finished webhook: %s", webhook_err)

            return {"ok": True, "job_id": job_id, "status": "completed"}

        except Exception as exc:
            logger.exception("process_bulk_job_task failed for %s: %s", job_id, exc)

            # Mark failed
            job.status = "failed"
            job.error_message = str(exc)[:2000]
            db.add(job)
            db.commit()

            # FIRE WEBHOOK ON FAILURE TOO (very important for UX!)
            try:
                trigger_webhook.delay(
                    "bulk_job.failed",
                    {
                        "job_id": job.job_id,
                        "error": str(exc),
                        "total": job.total or 0,
                        "processed": job.processed or 0,
                    },
                    team_id=job.team_id or job.user_id
                )
            except Exception as webhook_err:
                logger.warning("Failed to trigger bulk_job.failed webhook: %s", webhook_err)

            raise  # Let Celery retry or mark as failed

    except Exception as e:
        logger.exception("Unexpected error in bulk task %s", job_id)
        raise
    finally:
        try:
            db.close()
        except:
            pass
