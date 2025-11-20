from backend.app.celery_app import celery_app

@celery_app.task(name="backend.app.workers.decision_maker_tasks.fetch_decision_maker")
def fetch_decision_maker(domain: str, job_id: str, user_id: int):
    """
    TODO:
    Use pdl_client or apollo_client to retrieve employees.
    """
    return {
        "job_id": job_id,
        "domain": domain,
        "status": "pending (not implemented)"
}
