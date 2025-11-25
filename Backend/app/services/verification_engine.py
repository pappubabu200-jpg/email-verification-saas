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
    acquire_slot,
    release_slot,
)

from backend.app.services.deliverability_monitor import (
    record_domain_result,
    compute_domain_score,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------
# ASYNC VERIFICATION PIPELINE
# ---------------------------------------------------------

async def verify_email_async(
    email: str,
    user_id: int | None = None
) -> Dict[str, Any]:
    """
    Production verification pipeline.
    """

    # -----------------------------------------
    # 1) CACHE LOOKUP
    # -----------------------------------------
    cached = get_cached(email)
    if cached:
        domain = email.split("@")[-1].lower()
        try:
            record_domain_result(domain, cached.get("status") == "valid")
        except Exception:
            pass
        return cached

    # -----------------------------------------
    # 2) FORMAT VALIDATION
    # -----------------------------------------
    if "@" not in email:
        data = {"email": email, "status": "invalid", "reason": "no_at_symbol"}
        set_cached(email, data)
        return data

    local, domain = email.split("@", 1)
    domain = domain.lower()

    # -----------------------------------------
    # 3) MX LOOKUP
    # -----------------------------------------
    mx_hosts = choose_mx_for_domain(domain)
    if not mx_hosts:
        data = {"email": email, "status": "invalid", "reason": "no_mx"}
        set_cached(email, data)
        record_domain_result(domain, False)
        return data

    # -----------------------------------------
    # 4) DOMAIN BACKOFF RESPECT
    # -----------------------------------------
    backoff_sec = get_backoff_seconds(domain)
    if backoff_sec > 0:
        await asyncio.sleep(min(backoff_sec, 8))

    # -----------------------------------------
    # 5) CONCURRENCY SLOT ACQUIRE
    # -----------------------------------------
    if not acquire_slot(domain):
        return {"email": email, "status": "unknown", "reason": "domain_slots_full"}

    # -----------------------------------------
    # 6) SMTP PROBE (FIXED SIGNATURE)
    # -----------------------------------------
    try:
        smtp_res = await smtp_probe(email, mx_hosts)
    except Exception as e:
        logger.exception("SMTP probe failed: %s", e)
        smtp_res = {"email": email, "status": "error", "exception": str(e)}
        increase_backoff(domain)
    finally:
        release_slot(domain)

    # -----------------------------------------
    # 7) SCORING ENGINE
    # -----------------------------------------
    scored = score_verification(smtp_res)

    # -----------------------------------------
    # 8) DELIVERABILITY TRACKING
    # -----------------------------------------
    try:
        record_domain_result(domain, scored.get("status") == "valid")
    except Exception:
        pass

    # -----------------------------------------
    # 9) DOMAIN REPUTATION SCORE
    # -----------------------------------------
    try:
        mx_used = smtp_res.get("mx_host")
        scored["domain_reputation"] = compute_domain_score(domain, mx_used)
    except Exception:
        scored["domain_reputation"] = None

    # -----------------------------------------
    # 10) CACHE SAVE
    # -----------------------------------------
    set_cached(email, scored)

    # -----------------------------------------
    # 11) DATABASE PERSISTENCE
    # -----------------------------------------
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
    except Exception as e:
        logger.exception("DB insert failed: %s", e)
    finally:
        db.close()

    return scored


# ---------------------------------------------------------
# SAFE SYNC WRAPPER (NO event-loop crash)
# ---------------------------------------------------------

def verify_email_sync(email: str, user_id: int | None = None) -> Dict[str, Any]:
    """
    Run async verifier safely in sync context.
    """

    try:
        loop = asyncio.get_running_loop()
        # Already in event loop → run in executor
        return loop.run_until_complete(verify_email_async(email, user_id))
    except RuntimeError:
        # No running loop → safe to call asyncio.run
        return asyncio.run(verify_email_async(email, user_id))
