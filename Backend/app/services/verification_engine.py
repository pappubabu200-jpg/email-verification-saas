import json
import uuid
import logging
from typing import Dict, Optional

from backend.app.db import SessionLocal
from backend.app.services.mx_lookup import choose_mx_for_domain
from backend.app.services.smtp_probe import smtp_probe
from backend.app.services.cache import get_cached, set_cached
from backend.app.services.verification_score import score_verification
from backend.app.models.verification_result import VerificationResult

logger = logging.getLogger(__name__)

def _split_local_domain(email: str):
    if "@" not in email:
        return email, ""
    local, domain = email.split("@", 1)
    return local, domain.lower()

def verify_email_sync(email: str, user_id: Optional[int] = None) -> Dict:
    """
    Synchronous verification flow for single checks:
    - return cached if present
    - resolve MX
    - smtp probe
    - score
    - persist result
    - cache result
    """
    # check cache
    cached = get_cached(email)
    if cached:
        cached["cached"] = True
        return cached

    local, domain = _split_local_domain(email)
    if not domain:
        result = {"email": email, "status": "invalid", "reason": "no_domain"}
        set_cached(email, result)
        return result

    mx_hosts = choose_mx_for_domain(domain)
    if not mx_hosts:
        result = {"email": email, "status": "invalid", "reason": "no_mx"}
        set_cached(email, result)
        return result

    probe = smtp_probe(email, mx_hosts)
    scored = score_verification(probe)
    # add some common fields
    scored.update({"email": email, "cached": False})
    # persist in DB
    try:
        db = SessionLocal()
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
        db.refresh(vr)
    except Exception as e:
        logger.exception("Failed to persist verification_result: %s", e)
    finally:
        try:
            db.close()
        except Exception:
            pass

    # cache the scored result
    try:
        set_cached(email, scored)
    except Exception:
        pass

    return scored
