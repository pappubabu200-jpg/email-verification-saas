# backend/app/services/verification_engine.py

import json
import logging
import asyncio
from typing import Any, Dict

from backend.app.db import SessionLocal
from backend.app.models.verification_result import VerificationResult

from backend.app.services.cache import get_cached, set_cached
from backend.app.services.mx_lookup import choose_mx_for_domain
from backend.app.services.smtp_probe import smtp_probe
from backend.app.services.verification_score import score_verification
from backend.app.services.domain_backoff import (
    get_backoff_seconds,
    increase_backoff,
    clear_backoff,
    acquire_slot,
    release_slot,
)
from backend.app.services.deliverability_monitor import (
    record_domain_result,
    compute_domain_score,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------
# ASYNC ENGINE
# ---------------------------------------------------------

async def verify_email_async(email: str, user_id: int | None = None) -> Dict[str, Any]:
    """
    Full async verification pipeline:
    - cache
    - MX lookup
    - SMTP handshake
    - scoring
    - deliverability tracking
    - persistence
    """
    # ---------- CACHE ----------
    cached = get_cached(email)
    if cached:
        domain = email.split("@")[-1].lower()
        try:
            record_domain_result(domain, cached.get("status") == "valid")
        except Exception:
            pass
        return cached

    # ---------- FORMAT CHECK ----------
    if "@" not in email:
        result = {"email": email, "status": "invalid", "reason": "no_at_symbol"}
        set_cached(email, result)
        return result

    local, domain = email.split("@", 1)
    domain = domain.lower()

    # ---------- MX LOOKUP ----------
    mx_hosts = choose_mx_for_domain(domain)
    if not mx_hosts:
        result = {"email": email, "status": "invalid", "reason": "no_mx"}
        set_cached(email, result)
        record_domain_result(domain, False)
        return result

    # ---------- RESPECT BACKOFF ----------
    backoff_sec = get_backoff_seconds(domain)
    if backoff_sec > 0:
        await asyncio.sleep(min(backoff_sec, 8))

    # ---------- DOMAIN SLOT (concurrency limiter) ----------
    slot_ok = acquire_slot(domain)
    if not slot_ok:
        result = {"email": email, "status": "unknown", "reason": "domain_slots_full"}
        return result

    # ---------- SMTP PROBE ----------
    try:
        smtp_res = await smtp_probe(email, domain, mx_hosts)
    except Exception as e:
        logger.exception("smtp probe failed: %s", e)
        smtp_res = {"status": "error", "exception": str(e)}
        increase_backoff(domain)
    finally:
        release_slot(domain)

    # ---------- SCORING ----------
    scored = score_verification(smtp_res)

    # ---------- DELIVERABILITY TRACKING ----------
    try:
        record_domain_result(domain, scored.get("status") == "valid")
    except Exception:
        pass

    # ---------- DOMAIN REPUTATION ----------
    try:
        mx_used = smtp_res.get("mx_host")
        scored["domain_reputation"] = compute_domain_score(domain, mx_used)
    except Exception:
        scored["domain_reputation"] = None

    # ---------- CACHE SAVE ----------
    set_cached(email, scored)

    # ---------- DB SAVE ----------
    db = SessionLocal()
    try:
        vr = VerificationResult(
            user_id=user_id,
            job_id=None,
            email=email,
            status=scored.get("status", "unknown"),
            risk_score=int(scored.get("risk_score", 50)),
            raw=json.dumps(scored),
            cached=False,
        )
        db.add(vr)
        db.commit()
    except Exception as e:
        logger.exception("DB insert failed: %s", e)
    finally:
        db.close()

    return scored


# ---------------------------------------------------------
# SYNC WRAPPER
# ---------------------------------------------------------

def verify_email_sync(email: str, user_id: int = None) -> Dict[str, Any]:
    """
    Sync wrapper so routers & bulk processor can call easily.
    """
    return asyncio.run(verify_email_async(email, user_id))
