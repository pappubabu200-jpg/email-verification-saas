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
# backend/app/workers/extractor_tasks.py
import logging
from celery import shared_task
from backend.app.db import SessionLocal
from backend.app.models.extractor_job import ExtractorJob
from backend.app.services.extractor_engine import extract_url
from backend.app.services.credits_service import capture_reservation_and_charge, release_reservation_by_job
from backend.app.services.pricing_service import get_cost_for_key
from decimal import Decimal

logger = logging.getLogger(__name__)

@shared_task(bind=True, name="process_extractor_job")
def process_extractor_job(self, job_id: str, estimated_cost: float):
    db = SessionLocal()
    try:
        job = db.query(ExtractorJob).filter(ExtractorJob.job_id == job_id).first()
        if not job:
            return {"error": "job_not_found"}

        results = []
        success = 0
        for url in job.urls:
            try:
                res = extract_url(url)
                results.append({"url": url, "result": res})
                if res.get("emails"):
                    success += 1
            except Exception:
                results.append({"url": url, "error": "extract_failed"})

        job.status = "finished"
        job.result_preview = str(results[:50])
        db.add(job); db.commit()

        # compute actual cost and finalize reservations similar to bulk
        per_cost = Decimal(str(get_cost_for_key("extractor.bulk_per_url") or 0))
        actual_cost = (per_cost * Decimal(len(job.urls))).quantize(Decimal("0.000001"))

        # find reservations and capture/release as in bulk worker
        # ... (reuse capture_reservation_and_charge & release_reservation_by_job)
        return {"ok": True, "processed": len(job.urls), "success": success}
    finally:
        db.close()
