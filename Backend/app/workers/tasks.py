from backend.app.celery_app import celery_app
from backend.app.services.verification_engine import verify_email_sync


@celery_app.task(name="backend.app.workers.tasks.verify_email_task", bind=True)
def verify_email_task(self, email: str, context: dict = None):
    """
    Celery worker task for verifying a single email.
    This task is called for both single and bulk jobs.
    """
    user_id = None
    job_id = None

    if context:
        user_id = context.get("user_id")
        job_id = context.get("job_id")

    result = verify_email_sync(email, user_id=user_id)

    # Add job_id so the watcher can group results per job
    result["job_id"] = job_id

    return result

from backend.app.celery_app import celery_app
import redis
import json

try:
    REDIS = redis.from_url("redis://redis:6379/0")
except:
    REDIS = None

@celery_app.task(bind=True)
def verify_email_task(self, email: str, context: dict):
    """
    Each verification increments Redis counters:
    job:{id}:done → +1
    on failure → job:{id}:error → +1
    """
    from backend.app.services.verification_engine import verify_email_sync

    job_id = context.get("job_id")
    reservation_id = context.get("reservation_id")
    user_id = context.get("user_id")

    try:
        result = verify_email_sync(email, user_id=user_id)
        if REDIS:
            REDIS.incr(f"job:{job_id}:done")
        return result
    except Exception:
        if REDIS:
            REDIS.incr(f"job:{job_id}:error")
        raise
        
