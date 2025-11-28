okfrom backend.app.celery_app import celery_app

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

# backend/app/workers/decision_maker_tasks.py
import logging
from backend.app.celery_app import celery_app
from backend.app.services.dm_autodiscovery import discover

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, name="workers.decision_maker_tasks.autodiscover_job", max_retries=1)
def autodiscover_job(self, job_id: str, domain: str = None, company_name: str = None, max_results: int = 100, user_id: int = None):
    """
    Celery task wrapper for domain/company autodiscovery.
    """
    logger.info(f"[DM Worker] Start autodiscover job {job_id} - {domain or company_name}")
    try:
        results = discover(domain=domain, company_name=company_name, max_results=max_results, job_id=job_id, user_id=user_id)
        logger.info(f"[DM Worker] Completed job {job_id} - found {len(results)} items")
        return {"job_id": job_id, "count": len(results)}
    except Exception as exc:
        logger.exception(f"[DM Worker] Failure for job {job_id}: {exc}")
        # worker-level broadcast and alerts can be done inside discover, but also here if needed
        raise
# backend/app/workers/decision_maker_tasks.py
import json
import logging
import traceback
import datetime
import asyncio
from typing import Optional

from celery import shared_task

from backend.app.db import SessionLocal
from backend.app.models.decision_maker import DecisionMaker
from backend.app.services.apollo_client import ApolloClient
from backend.app.services.pdl_client import PDLClient
from backend.app.services.verification_engine import verify_email_sync
from backend.app.services.dm_ws_manager import dm_ws_manager
from backend.app.services.credits_service import deduct_credits  # best-effort
from backend.app.services.cache import set_cached  # optional: invalidate cache after enrichment

logger = logging.getLogger(__name__)


def _safe_broadcast_job(job_id: str, payload: dict):
    """Best-effort async broadcast wrapper for dm_ws_manager."""
    try:
        # dm_ws_manager.broadcast_job may be async; use asyncio.run to fire-and-forget
        asyncio.run(dm_ws_manager.broadcast_job(job_id, payload))
    except Exception:
        try:
            # fallback to any sync API
            if hasattr(dm_ws_manager, "broadcast_job_sync"):
                dm_ws_manager.broadcast_job_sync(job_id, payload)
        except Exception:
            logger.debug("dm_ws broadcast failed: %s", payload)


def _merge_enrichment(apollo_res: dict | None, pdl_res: dict | None, verify_res: dict | None) -> dict:
    """Combine multiple enrichment sources into a single object."""
    out = {"apollo": None, "pdl": None, "verification": None, "merged_at": datetime.datetime.utcnow().isoformat()}
    if apollo_res:
        out["apollo"] = apollo_res
    if pdl_res:
        out["pdl"] = pdl_res
    if verify_res:
        out["verification"] = verify_res
    # derive quick summary fields
    summary = {}
    if apollo_res:
        summary["name"] = apollo_res.get("name") or apollo_res.get("full_name")
        summary["title"] = apollo_res.get("title")
        summary["company"] = apollo_res.get("company") or apollo_res.get("current_employer")
    if pdl_res:
        summary.setdefault("phone", pdl_res.get("phone"))
        summary.setdefault("linkedin", pdl_res.get("linkedin"))
    if verify_res:
        summary["email_status"] = verify_res.get("status")
        summary["risk_score"] = verify_res.get("risk_score")
    out["summary"] = summary
    return out


@shared_task(bind=True, name="workers.decision_maker_tasks.enrich_dm_task", soft_time_limit=120, time_limit=300)
def enrich_dm_task(self, dm_id: str, task_id: Optional[str] = None, user_id: Optional[int] = None):
    """
    Celery task to fully enrich a DecisionMaker record:
      - Apollo enrich (by email or name/company)
      - PDL enrich (by email)
      - SMTP/verification check (if email exists)
      - Persist enrichment JSON to DecisionMaker.enrichment_json
      - Broadcast progress via dm_ws_manager
      - Deduct credits (best-effort)
    Args:
      dm_id: id of DecisionMaker model (pk or uuid depending on your model)
      task_id: optional client-visible task id used by frontend
      user_id: optional user performing the enrichment (for billing/credits)
    """
    logger.info("Enrichment task start: dm_id=%s task_id=%s", dm_id, task_id)

    db = SessionLocal()
    try:
        dm = db.query(DecisionMaker).filter(DecisionMaker.id == dm_id).first()
        if not dm:
            logger.error("DecisionMaker not found for enrichment: %s", dm_id)
            _safe_broadcast_job(task_id or dm_id, {"event": "failed", "error": "dm_not_found", "dm_id": dm_id})
            return {"status": "failed", "reason": "dm_not_found"}

        # Broadcast start
        _safe_broadcast_job(task_id or dm_id, {"event": "enrich_started", "task_id": task_id, "dm_id": dm_id})

        apollo_res = None
        pdl_res = None
        verify_res = None

        # Step 1: Apollo enrich (prefer by email)
        try:
            ap = ApolloClient()
            if dm.email:
                # use email-based enrichment if Apollo supports it
                try:
                    apollo_res = ap.enrich_person_by_email(dm.email)
                except Exception:
                    # fallback to search by name+company
                    apollo_res = ap.enrich_person_by_name_company(name=dm.name, company=dm.company or dm.company_domain)
            else:
                apollo_res = ap.enrich_person_by_name_company(name=dm.name, company=dm.company or dm.company_domain)
            logger.debug("Apollo enrich done for %s", dm_id)
            _safe_broadcast_job(task_id or dm_id, {"event": "progress", "step": "apollo_done", "dm_id": dm_id})
        except Exception as e:
            logger.exception("Apollo enrichment failed for %s: %s", dm_id, e)
            # do not fail completely; continue with PDL/verification

        # Step 2: PDL enrich (by email if available)
        try:
            pdl = PDLClient()
            if dm.email:
                pdl_res = pdl.enrich_email(dm.email)
            else:
                # optionally enrich by domain/company; here we try by email only
                pdl_res = None
            logger.debug("PDL enrich done for %s", dm_id)
            _safe_broadcast_job(task_id or dm_id, {"event": "progress", "step": "pdl_done", "dm_id": dm_id})
        except Exception as e:
            logger.exception("PDL enrichment failed for %s: %s", dm_id, e)

        # Step 3: Verification check (SMTP / pattern) if email present or if apollo found email
        email_to_check = dm.email or (apollo_res and apollo_res.get("email"))
        if email_to_check:
            try:
                verify_res = verify_email_sync(email_to_check, user_id=user_id)
                logger.debug("Verify result for %s -> %s", email_to_check, verify_res.get("status"))
                _safe_broadcast_job(task_id or dm_id, {"event": "progress", "step": "verify_done", "dm_id": dm_id})
            except Exception as e:
                logger.exception("Verification call failed for %s: %s", email_to_check, e)

        # Step 4: Merge results
        merged = _merge_enrichment(apollo_res, pdl_res, verify_res)

        # Persist enrichment_json and update fields on model (best-effort)
        try:
            dm.enrichment_json = merged
            # update top-level email/phone if missing
            if not dm.email and merged["summary"].get("email_status") is not None and (apollo_res and apollo_res.get("email")):
                dm.email = apollo_res.get("email")
            if not getattr(dm, "phone", None) and pdl_res and pdl_res.get("phone"):
                dm.phone = pdl_res.get("phone")
            if hasattr(dm, "updated_at"):
                dm.updated_at = datetime.datetime.utcnow()
            db.add(dm)
            db.commit()
            logger.info("Enrichment persisted for dm_id=%s", dm_id)
            _safe_broadcast_job(task_id or dm_id, {"event": "progress", "step": "persisted", "dm_id": dm_id})
        except Exception as e:
            db.rollback()
            logger.exception("Failed to persist enrichment for %s: %s", dm_id, e)
            _safe_broadcast_job(task_id or dm_id, {"event": "failed", "error": "persist_failed", "dm_id": dm_id})
            return {"status": "failed", "reason": "persist_failed"}

        # Step 5: Deduct credits (best-effort)
        if user_id:
            try:
                deduct_credits(user_id, 1, reason="dm_enrich")
            except Exception as e:
                # log but do not fail
                logger.debug("Credit deduction failed (ignored): %s", e)

        # Broadcast completion
        _safe_broadcast_job(task_id or dm_id, {
            "event": "enrich_completed",
            "dm_id": dm_id,
            "task_id": task_id,
            "enrichment_summary": merged.get("summary", {}),
        })

        # Optional: invalidate or update cache for DM detail
        try:
            if getattr(dm, "company_domain", None):
                cache_key = f"dm:detail:{dm.email or dm.id}"
                try:
                    set_cached(cache_key, merged, ttl=60 * 60 * 24)
                except Exception:
                    pass
        except Exception:
            pass

        return {"status": "ok", "dm_id": dm_id, "task_id": task_id}

    except Exception as exc:
        logger.exception("Uncaught exception in enrich_dm_task for %s: %s", dm_id, exc)
        try:
            _safe_broadcast_job(task_id or dm_id, {
                "event": "failed",
                "dm_id": dm_id,
                "error": "task_error",
                "trace": traceback.format_exc()[:2000],
            })
        except Exception:
            pass
        raise

    finally:
        try:
            db.close()
        except Exception:
            pass

