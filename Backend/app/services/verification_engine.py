# backend/app/services/verification_engine.py

import json
import logging
import asyncio
from typing import Any, Dict, Optional

from backend.app.db import SessionLocal
from backend.app.models.verification_result import VerificationResult

# NOTE: many of these services are synchronous (blocking).
# We will call them via asyncio.to_thread(...) to avoid blocking the event loop.
from backend.app.services.cache import get_cached, set_cached
from backend.app.services.mx_lookup import choose_mx_for_domain
from backend.app.services.smtp_probe import smtp_probe
from backend.app.services.verification_score import score_verification

from backend.app.services.domain_backoff import (
    get_backoff_seconds,
    increase_backoff,
    acquire_slot,
    release_slot,
)

from backend.app.services.deliverability_monitor import (
    record_domain_result,
    compute_domain_score,
)

# NEW: processing lock
from backend.app.services.processing_lock import (
    acquire_processing_key,
    release_processing_key,
    wait_for_processing_result,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------
# ASYNC VERIFICATION PIPELINE (non-blocking)
# ---------------------------------------------------------

async def _to_thread(func, *args, **kwargs):
    """Helper to run blocking functions in a threadpool."""
    return await asyncio.to_thread(func, *args, **kwargs)


async def verify_email_async(
    email: str,
    user_id: Optional[int] = None
) -> Dict[str, Any]:
    """
    Production verification pipeline (async). All blocking calls are executed
    with asyncio.to_thread to avoid blocking the event loop.
    """

    email = (email or "").strip()
    if not email:
        return {"email": email, "status": "invalid", "reason": "empty_email"}

    # -----------------------------------------------------
    # 1) CACHE LOOKUP
    # -----------------------------------------------------
    try:
        cached = await _to_thread(get_cached, email)
    except Exception as e:
        logger.warning("Cache lookup failed (allowing miss): %s", e)
        cached = None

    if cached:
        domain = email.split("@")[-1].lower()
        try:
            await _to_thread(record_domain_result, domain, cached.get("status") == "valid")
        except Exception:
            pass
        return cached

    # -----------------------------------------------------
    # 1.5) PROCESSING LOCK (DEDUPE)
    # -----------------------------------------------------
    got_lock = await acquire_processing_key(email, ttl=60)

    if not got_lock:
        # Another worker is verifying this email
        maybe = await wait_for_processing_result(email, poll_interval=0.5, timeout=30)
        if maybe:
            return maybe
        # Fail-open: continue to verification

    # -----------------------------------------------------
    # 2) FORMAT VALIDATION
    # -----------------------------------------------------
    if "@" not in email:
        data = {"email": email, "status": "invalid", "reason": "no_at_symbol"}
        try:
            await _to_thread(set_cached, email, data)
        except Exception:
            logger.debug("Cache set failed for invalid email")

        # release lock before returning
        try:
            await release_processing_key(email)
        except Exception:
            pass

        return data

    local, domain = email.split("@", 1)
    domain = domain.lower()

    # -----------------------------------------------------
    # 3) MX LOOKUP
    # -----------------------------------------------------
    try:
        mx_hosts = await _to_thread(choose_mx_for_domain, domain)
    except Exception as e:
        logger.exception("MX lookup failed (treat as no_mx): %s", e)
        mx_hosts = []

    if not mx_hosts:
        data = {"email": email, "status": "invalid", "reason": "no_mx"}
        try:
            await _to_thread(set_cached, email, data)
            await _to_thread(record_domain_result, domain, False)
        except Exception:
            pass

        # release lock
        try:
            await release_processing_key(email)
        except Exception:
            pass

        return data

    # -----------------------------------------------------
    # 4) DOMAIN BACKOFF
    # -----------------------------------------------------
    try:
        backoff_sec = await _to_thread(get_backoff_seconds, domain)
    except Exception as e:
        logger.warning("get_backoff_seconds error: %s", e)
        backoff_sec = 0

    if backoff_sec and backoff_sec > 0:
        await asyncio.sleep(min(backoff_sec, 8))

    # -----------------------------------------------------
    # 5) SLOT ACQUIRE
    # -----------------------------------------------------
    try:
        slot_acquired = await _to_thread(acquire_slot, domain)
    except Exception as e:
        logger.warning("acquire_slot error (allowing attempt): %s", e)
        slot_acquired = True

    if not slot_acquired:
        # release processing lock before returning
        try:
            await release_processing_key(email)
        except Exception:
            pass

        return {"email": email, "status": "unknown", "reason": "domain_slots_full"}

    # -----------------------------------------------------
    # 6) SMTP PROBE
    # -----------------------------------------------------
    smtp_res = None
    try:
        smtp_res = await smtp_probe(email, mx_hosts)
    except Exception as e:
        logger.exception("SMTP probe failed: %s", e)
        try:
            await _to_thread(increase_backoff, domain)
        except Exception:
            pass
        smtp_res = {"email": email, "status": "error", "exception": str(e)}
    finally:
        try:
            await _to_thread(release_slot, domain)
        except Exception:
            logger.warning("release_slot failed")

    # -----------------------------------------------------
    # 7) SCORING
    # -----------------------------------------------------
    try:
        scored = await _to_thread(score_verification, smtp_res)
    except Exception as e:
        logger.exception("Scoring failed: %s", e)
        scored = {"email": email, "status": "unknown", "risk_score": 50, "raw": smtp_res}

    # -----------------------------------------------------
    # 8) DOMAIN TRACKING
    # -----------------------------------------------------
    try:
        await _to_thread(record_domain_result, domain, scored.get("status") == "valid")
    except Exception:
        pass

    # -----------------------------------------------------
    # 9) DOMAIN REPUTATION
    # -----------------------------------------------------
    try:
        mx_used = smtp_res.get("mx_host") if isinstance(smtp_res, dict) else None
        reputation = await _to_thread(compute_domain_score, domain, mx_used)
        scored["domain_reputation"] = reputation
    except Exception:
        scored["domain_reputation"] = None

    scored.setdefault("email", email)
    scored.setdefault("risk_score", scored.get("risk_score", 50))

    # -----------------------------------------------------
    # 10) CACHE SAVE
    # -----------------------------------------------------
    try:
        await _to_thread(set_cached, email, scored)
    except Exception:
        logger.debug("Cache save failed")

    # -----------------------------------------------------
    # 11) DB SAVE
    # -----------------------------------------------------
    try:
        await _to_thread(_persist_verification_result, email, user_id, scored)
    except Exception as e:
        logger.exception("DB persist failed: %s", e)

    # -----------------------------------------------------
    # RELEASE PROCESSING LOCK (always)
    # -----------------------------------------------------
    try:
        await release_processing_key(email)
    except Exception:
        pass

    return scored


# DB persistence helper
def _persist_verification_result(email: str, user_id: Optional[int], scored: Dict[str, Any]):
    db = SessionLocal()
    try:
        vr = VerificationResult(
            user_id=user_id,
            job_id=None,
            email=email,
            status=scored.get("status"),
            risk_score=int(scored.get("risk_score", 50)),
            raw=json.dumps(scored),
            cached=False,
        )
        db.add(vr)
        db.commit()
    except Exception:
        try:
            db.rollback()
        except Exception:
            pass
        raise
    finally:
        try:
            db.close()
        except Exception:
            pass


# ---------------------------------------------------------
# SAFE SYNC WRAPPER
# ---------------------------------------------------------
def verify_email_sync(email: str, user_id: Optional[int] = None) -> Dict[str, Any]:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(verify_email_async(email, user_id))
    else:
        import concurrent.futures
        def _runner():
            return asyncio.run(verify_email_async(email, user_id))
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
            return ex.submit(_runner).result()
