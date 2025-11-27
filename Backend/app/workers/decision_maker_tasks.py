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

# backend/app/workers/decision_maker_tasks.py
import asyncio
import logging
from celery import shared_task

from backend.app.services.decision_maker_service import (
    get_decision_maker_detail
)
from backend.app.services.cache import set_cached

logger = logging.getLogger(__name__)


@shared_task(name="dm.enrich.async")
def dm_enrich_async(uid: str, user_id: int | None = None):
    """
    Background enrichment task.
    Runs PDL + Apollo deep enrichment and patches cache with final data.
    """
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        detail = loop.run_until_complete(
            get_decision_maker_detail(uid, user_id)
        )

        # Save back to cache (1h default)
        if detail:
            set_cached(f"dm:detail:{uid.lower()}", detail, ttl=3600)

        return {"ok": True, "uid": uid}

    except Exception as e:
        logger.exception("Background enrichment failed for %s: %s", uid, e)
        return {"ok": False, "error": str(e)}
