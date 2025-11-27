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
        
celery_app.conf.beat_schedule.update({
    "recover-dead-jobs-every-10min": {
        "task": "backend.app.workers.scheduler.recover_dead_jobs",
        "schedule": 600,   # 10 minutes
    }
})
from backend.app.services.minio_client import delete_object_if_exists

@celery_app.task
def cleanup_old_outputs():
    THRESHOLD_DAYS = 14
    db = SessionLocal()
    try:
        cutoff = datetime.utcnow() - timedelta(days=THRESHOLD_DAYS)
        old_jobs = db.query(BulkJob).filter(
            BulkJob.created_at < cutoff,
            BulkJob.output_path != None
        ).all()

        for job in old_jobs:
            try:
                path = job.output_path.replace("s3://", "").split("/", 1)[1]
                delete_object_if_exists(path)
            except Exception as e:
                logger.error("cleanup failed for %s: %s", job.output_path, e)
    finally:
        db.close()

@router.get("/my-jobs")
def list_my_jobs(
    status: str = None,
    page: int = 1,
    per_page: int = 20,
    current_user = Depends(get_current_user)
):
    db = SessionLocal()
    q = db.query(BulkJob).filter(BulkJob.user_id == current_user.id)

    if status:
        q = q.filter(BulkJob.status == status)

    total = q.count()
    jobs = q.order_by(BulkJob.created_at.desc())\
            .limit(per_page)\
            .offset((page - 1) * per_page)\
            .all()

from backend.app.services.ws.admin_metrics_ws import admin_metrics_ws

@app.on_after_configure.connect
def setup_periodic_tasks(sender, **kwargs):
    sender.add_periodic_task(5.0, send_admin_metrics.s())

@celery_app.task
def send_admin_metrics():
    # read stats from DB or Redis
    payload = {
        "type": "metrics",
        "credits": {...},
        "verifications": [...],
        "deliverability": {...},
        "events": [...]
    }
    asyncio.run(admin_metrics_ws.broadcast(payload))


