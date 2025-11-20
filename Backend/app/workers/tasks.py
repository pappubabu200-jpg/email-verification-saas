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
