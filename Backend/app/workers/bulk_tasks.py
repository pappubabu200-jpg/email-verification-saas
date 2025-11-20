from backend.app.celery_app import celery_app
from backend.app.services.bulk_processor import submit_bulk_job


@celery_app.task(name="backend.app.workers.bulk_tasks.enqueue_bulk")
def enqueue_bulk(user_id: int, job_id: str, emails: list):
    """
    External entry point if you want to enqueue bulk jobs from Celery.
    Not required for now but kept for scaling.
    """
    return submit_bulk_job(user_id, job_id, emails)
