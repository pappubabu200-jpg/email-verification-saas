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
# ASYNC VERIFICATION PIPELINE
# ---------------------------------------------------------

async def verify_email_async(
    email: str, 
    user_id: int | None = None
) -> Dict[str, Any]:
    """
    Full production email verification flow:
      ✔ Cache lookup
      ✔ MX lookup
      ✔ Domain backoff wait
      ✔ Slot-based concurrency limiter
      ✔ SMTP probe (async/sync hybrid)
      ✔ Risk scoring
      ✔ Deliverability tracking
      ✔ Domain reputation score
      ✔ Cache store
      ✔ Database persistence
    """

    # -----------------------------------------------------
    # 1) CACHE CHECK
    # -----------------------------------------------------
    cached = get_cached(email)
    if cached:
        domain = email.split("@")[-1].lower()
        try:
            record_domain_result(domain, cached.get("status") == "valid")
        except Exception:
            pass
        return cached

    # -----------------------------------------------------
    # 2) BASIC FORMAT CHECK
    # -----------------------------------------------------
    if "@" not in email:
        result = {
            "email": email,
            "status": "invalid",
            "reason": "no_at_symbol"
        }
        set_cached(email, result)
        return result

    local, domain = email.split("@", 1)
    domain = domain.lower()

    # -----------------------------------------------------
    # 3) MX LOOKUP
    # -----------------------------------------------------
    mx_hosts = choose_mx_for_domain(domain)
    if not mx_hosts:
        result = {
            "email": email,
            "status": "invalid",
            "reason": "no_mx"
        }
        set_cached(email, result)
        record_domain_result(domain, False)
        return result

    # -----------------------------------------------------
    # 4) RESPECT DOMAIN BACKOFF
    # -----------------------------------------------------
    backoff_sec = get_backoff_seconds(domain)
    if backoff_sec > 0:
        await asyncio.sleep(min(backoff_sec, 8))

    # -----------------------------------------------------
    # 5) DOMAIN SLOT ACQUIRE (parallel limiter)
    # -----------------------------------------------------
    if not acquire_slot(domain):
        # Domain overloaded → temporary
        return {
            "email": email,
            "status": "unknown",
            "reason": "domain_slots_full"
        }

    # -----------------------------------------------------
    # 6) SMTP PROBE
    # -----------------------------------------------------
    try:
        smtp_res = await smtp_probe(email, mx_hosts)
    except Exception as e:
        logger.exception("SMTP probe failure: %s", e)
        smtp_res = {
            "email": email,
            "status": "error",
            "exception": str(e)
        }
        increase_backoff(domain)
    finally:
        release_slot(domain)

    # -----------------------------------------------------
    # 7) SCORING ENGINE (status + risk_score)
    # -----------------------------------------------------
    scored = score_verification(smtp_res)  # returns dict {status, risk_score, details, ...}

    # -----------------------------------------------------
    # 8) DELIVERABILITY TRACKING
    # -----------------------------------------------------
    try:
        is_valid = scored.get("status") == "valid"
        record_domain_result(domain, is_valid)
    except Exception:
        pass

    # -----------------------------------------------------
    # 9) DOMAIN REPUTATION SCORE
    # -----------------------------------------------------
    try:
        mx_used = smtp_res.get("mx_host")
        scored["domain_reputation"] = compute_domain_score(domain, mx_used)
    except Exception:
        scored["domain_reputation"] = None

    # -----------------------------------------------------
    # 10) STORE IN CACHE
    # -----------------------------------------------------
    set_cached(email, scored)

    # -----------------------------------------------------
    # 11) PERSIST RESULT IN DATABASE
    # -----------------------------------------------------
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
# SYNC WRAPPER (used by routers + bulk processor)
# ---------------------------------------------------------

def verify_email_sync(email: str, user_id: int | None = None) -> Dict[str, Any]:
    """Run async verification in sync mode."""
    return asyncio.run(verify_email_async(email, user_id))
