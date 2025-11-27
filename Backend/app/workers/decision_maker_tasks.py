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

# backend/app/workers/decision_maker_tasks.py
"""
Decision Maker Enrichment Worker
-----------------------------------
This Celery worker:
  ✓ Loads DM from DB
  ✓ Fetches Apollo data
  ✓ Fetches PDL data
  ✓ Merges intelligently
  ✓ Updates DB (enrichment_json + main fields)
  ✓ Broadcasts WebSocket events via dm_ws_manager
"""

import logging
import datetime
import json

from celery import shared_task
from sqlalchemy import select

from backend.app.db import SessionLocal
from backend.app.models.decision_maker import DecisionMaker
from backend.app.services.dm_ws_manager import dm_ws_manager

# External enrichment clients
from backend.app.services.apollo_client import ApolloClient
from backend.app.services.pdl_client import PDLClient

logger = logging.getLogger(__name__)


# -------------------------------------------------------
# Helper: Merge Apollo + PDL records into one dictionary
# -------------------------------------------------------
def merge_profiles(ap: dict | None, pdl: dict | None):
    """Merge Apollo + PDL result best-effort."""
    ap = ap or {}
    pdl = pdl or {}

    out = {}

    # Base name
    out["name"] = (
        ap.get("name")
        or pdl.get("full_name")
        or pdl.get("name")
        or ""
    )

    # Title
    out["title"] = (
        ap.get("title")
        or (pdl.get("employment") or {}).get("title")
        or ""
    )

    # Email
    out["email"] = (
        ap.get("email")
        or pdl.get("email")
    )

    # Company
    out["company"] = (
        ap.get("company_name")
        or (pdl.get("employment") or {}).get("organization")
        or ""
    )

    # Domain
    out["company_domain"] = (
        ap.get("company_domain")
        or pdl.get("domain")
        or ""
    )

    # Phone
    out["phone"] = (
        ap.get("phone")
        or pdl.get("phone")
    )

    # Social links
    out["linkedin"] = (
        ap.get("linkedin_url")
        or ap.get("linkedin")
        or pdl.get("linkedin")
    )
    out["twitter"] = ap.get("twitter")
    out["github"] = ap.get("github")

    # Location
    out["location"] = (
        ap.get("location")
        or pdl.get("location")
    )

    # Seniority
    out["seniority"] = (
        ap.get("seniority")
        or pdl.get("seniority")
    )

    # Department
    out["department"] = (
        ap.get("department")
        or pdl.get("department")
    )

    # Work history
    out["work_history"] = (
        pdl.get("employment_history")
        or ap.get("work_history")
        or []
    )

    # Entire raw data
    out["_raw"] = {
        "apollo": ap,
        "pdl": pdl
    }

    return out


# -------------------------------------------------------
# Celery Task
# -------------------------------------------------------
@shared_task(name="workers.decision_maker_tasks.enrich_dm_task", bind=True, max_retries=2)
def enrich_dm_task(self, dm_id: str, task_id: str):
    """
    Heavy enrichment task: runs Apollo + PDL and updates DB.
    Broadcasts progress via WebSocket.
    """
    logger.info(f"[DM-Worker] Start enrichment for {dm_id}")

    # WebSocket event: started
    try:
        import asyncio
        asyncio.run(dm_ws_manager.broadcast_dm(dm_id, {
            "event": "enrich_started",
            "dm_id": dm_id,
            "task_id": task_id
        }))
    except Exception:
        pass

    db = SessionLocal()
    try:
        stmt = select(DecisionMaker).where(DecisionMaker.id == dm_id)
        res = db.execute(stmt)
        dm = res.scalar_one_or_none()

        if not dm:
            logger.error(f"DM not found: {dm_id}")
            raise ValueError("DM not found")

        # Initialize clients
        try:
            apollo = ApolloClient()
        except Exception:
            apollo = None

        try:
            pdl = PDLClient()
        except Exception:
            pdl = None

        ap = None
        pdl_info = None

        # Apollo fetch
        if apollo:
            try:
                ap = apollo.enrich_person_by_email(dm.email) if dm.email else None
            except Exception as e:
                logger.debug(f"Apollo error: {e}")

        # progress event
        try:
            import asyncio
            asyncio.run(dm_ws_manager.broadcast_dm(dm_id, {
                "event": "enrich_progress",
                "step": "apollo",
            }))
        except Exception:
            pass

        # PDL fetch
        if pdl:
            try:
                pdl_info = pdl.fetch_person_by_email(dm.email) if dm.email else None
            except Exception as e:
                logger.debug(f"PDL error: {e}")

        # progress event
        try:
            import asyncio
            asyncio.run(dm_ws_manager.broadcast_dm(dm_id, {
                "event": "enrich_progress",
                "step": "pdl",
            }))
        except Exception:
            pass

        # Merge records
        merged = merge_profiles(ap, pdl_info)

        # Save enrichment JSON
        dm.enrichment_json = merged

        # Update common fields
        dm.name = merged.get("name") or dm.name
        dm.title = merged.get("title") or dm.title
        dm.email = merged.get("email") or dm.email
        dm.company = merged.get("company") or dm.company
        dm.company_domain = merged.get("company_domain") or dm.company_domain
        dm.phone = merged.get("phone") or dm.phone
        dm.linkedin = merged.get("linkedin") or dm.linkedin
        dm.twitter = merged.get("twitter") or dm.twitter
        dm.github = merged.get("github") or dm.github
        dm.location = merged.get("location") or dm.location
        dm.seniority = merged.get("seniority") or dm.seniority
        dm.department = merged.get("department") or dm.department

        dm.updated_at = datetime.datetime.utcnow()

        db.add(dm)
        db.commit()

        # WebSocket event: completed
        try:
            import asyncio
            asyncio.run(dm_ws_manager.broadcast_dm(dm_id, {
                "event": "enrich_completed",
                "dm_id": dm_id,
                "task_id": task_id,
                "merged": merged
            }))
        except Exception:
            pass

        logger.info(f"[DM-Worker] Finished enrichment for {dm_id}")
        return {"ok": True, "dm_id": dm_id}

    except Exception as exc:
        logger.exception(f"[DM-Worker] Failed for {dm_id}: {exc}")

        # WS failure event
        try:
            import asyncio
            asyncio.run(dm_ws_manager.broadcast_dm(dm_id, {
                "event": "enrich_failed",
                "dm_id": dm_id,
                "task_id": task_id,
                "error": str(exc),
            }))
        except:
            pass

        raise

    finally:
        db.close()

