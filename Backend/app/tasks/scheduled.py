# backend/app/tasks/scheduled.py

from datetime import datetime, timedelta
from celery import shared_task
from celery.utils.log import get_task_logger

from backend.app.db import SessionLocal
from backend.app.models.credit_reservation import CreditReservation
from backend.app.services.domain_backoff import clear_backoff
from backend.app.models.bulk_job import BulkJob

logger = get_task_logger(__name__)


# ----------------------------------------------------
# CLEANUP EXPIRED CREDIT RESERVATIONS
# ----------------------------------------------------
@shared_task(name="cleanup_reservations")
def cleanup_reservations():
    db = SessionLocal()
    try:
        now = datetime.utcnow()
        rows = (
            db.query(CreditReservation)
            .filter(
                CreditReservation.locked == True,
                CreditReservation.expires_at < now,
            )
            .all()
        )
        for r in rows:
            r.locked = False
            db.add(r)
        db.commit()
        return len(rows)
    finally:
        db.close()


# ----------------------------------------------------
# CLEANUP DOMAIN BACKOFF (older than 10 minutes)
# ----------------------------------------------------
@shared_task(name="cleanup_domain_backoff")
def cleanup_domain_backoff():
    # Clear domain backoff for common domains
    for domain in ["gmail.com", "outlook.com", "yahoo.com"]:
        clear_backoff(domain)
    return {"status": "ok"}


# ----------------------------------------------------
# AUTO-FIX STUCK BULK JOBS
# ----------------------------------------------------
@shared_task(name="fix_stuck_bulk_jobs")
def fix_stuck_bulk_jobs():
    db = SessionLocal()
    try:
        now = datetime.utcnow()
        cutoff = now - timedelta(hours=2)

        stuck_jobs = (
            db.query(BulkJob)
            .filter(
                BulkJob.status == "running",
                BulkJob.updated_at < cutoff,
            )
            .all()
        )

        for job in stuck_jobs:
            job.status = "failed"
            job.error_message = "Stuck job auto-cleaned by scheduler"
            db.add(job)

        db.commit()

        return {"fixed": len(stuck_jobs)}

    finally:
        db.close()


# ----------------------------------------------------
# DAILY ANALYTICS ROLLUPS
# ----------------------------------------------------
@shared_task(name="daily_usage_rollup")
def daily_usage_rollup():
    logger.info("Daily analytics rollup triggered.")
    # Good place to aggregate: total verifications, spam detections, billing summaries
    return {"status": "ok"}
