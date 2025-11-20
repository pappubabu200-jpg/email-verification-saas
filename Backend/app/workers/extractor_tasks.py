from backend.app.celery_app import celery_app

@celery_app.task(name="backend.app.workers.extractor_tasks.extract_from_url")
def extract_from_url(url: str, job_id: str, user_id: int):
    """
    TODO:
    Implement actual scraper (requests + bs4 + regex + JS fetch)
    """
    return {
        "job_id": job_id,
        "url": url,
        "emails": [],
        "status": "pending (not implemented)"
    }
