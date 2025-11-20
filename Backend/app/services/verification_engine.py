
import json
import logging
import time

from backend.app.models.verification_result import VerificationResult
from backend.app.db import SessionLocal
from backend.app.services.mx_lookup import choose_mx_for_domain
from backend.app.services.smtp_probe import smtp_probe
from backend.app.services.cache import get_cached, set_cached
from backend.app.services.domain_throttle import acquire, release
from backend.app.services.verification_score import score_verification

# NEW imports for deliverability engine
from backend.app.services.deliverability_monitor import (
    record_domain_result,
    compute_domain_score,
)

logger = logging.getLogger(__name__)


def verify_email_sync(email: str, user_id: int = None):
    """
    100% production version.
    Includes:
    - cache
    - throttling
    - smtp_probe
    - scoring
    - persistence
    - deliverability tracking
    """
    # -------- CACHE CHECK --------
    cached = get_cached(email)
    if cached:
        # also record historical: treat valid as "good"
        domain = email.split("@")[-1].lower()
        try:
            success = cached.get("status") == "valid"
            record_domain_result(domain, success)
        except Exception:
            pass
        return cached

    # -------- DOMAIN + MX --------
    if "@" not in email:
        result = {"email": email, "status": "invalid", "reason": "no_at_symbol"}
        set_cached(email, result)
        return result

    local, domain = email.split("@", 1)
    domain = domain.lower()

    mx_hosts = choose_mx_for_domain(domain)
    if not mx_hosts:
        result = {"email": email, "status": "invalid", "reason": "no_mx"}
        set_cached(email, result)
        record_domain_result(domain, False)
        return result

    # -------- SMTP PROBE --------
    probe = smtp_probe(email, mx_hosts)

    # -------- SCORING --------
    scored = score_verification(probe)  # returns {status, risk_score, details}

    # -------- DELIVERABILITY RECORDING --------
    try:
        success = scored.get("status") == "valid"
        record_domain_result(domain, success)
    except Exception as e:
        logger.debug("deliverability record failed: %s", e)

    # -------- OPTIONAL: DOMAIN SCORE PRE-COMPUTE --------
    try:
        mx_used = probe.get("mx_host")
        domain_rep = compute_domain_score(domain, mx_used)
        scored["domain_reputation"] = domain_rep
    except Exception:
        scored["domain_reputation"] = None

    # -------- CACHE STORE --------
    set_cached(email, scored)

    # -------- PERSIST IN DATABASE --------
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
