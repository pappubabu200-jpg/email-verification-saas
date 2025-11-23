# backend/app/workers/scheduler.py
from datetime import time
from celery.schedules import crontab
from backend.app.celery_app import celery_app
from backend.app.services.api_key_service import reset_all_api_keys_usage
import logging

logger = logging.getLogger(__name__)

# Schedule: run at 00:01 UTC every day (a minute after midnight)
@celery_app.on_after_configure.connect
def setup_periodic_tasks(sender, **kwargs):
    # daily reset at 00:01 UTC
    sender.add_periodic_task(
        crontab(minute=1, hour=0),
        reset_daily.s(),
        name="reset_api_key_usage_daily"
    )

@celery_app.task
def reset_daily():
    logger.info("Running daily API key usage reset")
    reset_all_api_keys_usage()
    logger.info("Completed daily API key usage reset")


# backend/app/workers/scheduler.py
from backend.app.celery_app import celery_app
from backend.app.services.credits_service import release_reservation_by_job
from backend.app.services.reservation_finalizer import finalize_reservations_for_job
from backend.app.db import SessionLocal
from backend.app.models.credit_reservation import CreditReservation
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

@celery_app.on_after_configure.connect
def setup_periodic_tasks(sender, **kwargs):
    # run cleanup every 10 minutes
    sender.add_periodic_task(600.0, cleanup_expired_reservations.s(), name="cleanup_expired_reservations")

@celery_app.task(name="cleanup_expired_reservations")
def cleanup_expired_reservations():
    db = SessionLocal()
    try:
        now = datetime.utcnow()
        expired = db.query(CreditReservation).filter(CreditReservation.expires_at < now, CreditReservation.locked == True).all()
        for r in expired:
            logger.info("releasing expired reservation %s", r.id)
            r.locked = False
            db.add(r)
        db.commit()
    finally:
        db.close()

from celery.schedules import crontab

celery_app.conf.beat_schedule.update({
    "bill-overages-monthly": {
        "task": "billing.monthly_overage_task",
        "schedule": crontab(hour=0, minute=0, day_of_month="1")
    }
})

@celery_app.task
def recover_dead_jobs():
    db = SessionLocal()
    try:
        stuck = db.query(BulkJob).filter(
            BulkJob.status.in_(["queued", "processing"])
        ).all()

        for job in stuck:
            # if job older than 45 minutes = dead
            if (datetime.utcnow() - job.created_at).seconds > 2700:
                job.status = "error"
                job.error_message = "auto_recovered_stuck_job"
                db.add(job)
        db.commit()
    finally:
        db.close()
        

