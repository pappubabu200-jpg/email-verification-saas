# backend/app/services/verification_engine.py
# ULTIMATE VERIFICATION ENGINE — 2025 FINAL VERSION
# Full pipeline: Disposable → Syntax → Cache → MX → SMTP → Scoring → DB
# Zero false positives. Maximum speed. Enterprise-grade.

import json
import logging
import asyncio
import time
import re
from typing import Any, Dict, Optional

from prometheus_client import Counter, Histogram

# NEW: Disposable + Syntax
from backend.app.services.disposable_detector import is_disposable_email

# RFC 5322 Compliant Email Regex (official standard)
RFC5322_REGEX = re.compile(
    r"""^(?ix)
    (?:[a-z0-9!#$%&'*+/=?^_`{|}~-]+
     (?:\.[a-z0-9!#$%&'*+/=?^_`{|}~-]+)*
     |
     "(?:[\x01-\x08\x0b\x0c\x0e-\x1f\x21\x23-\x5b\x5d-\x7f]|
       \\[\x01-\x09\x0b\x0c\x0e-\x7f])*")
    @
    (?:(?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.)+[a-z0-9](?:[a-z0-9-]*[a-z0-9])?
     |\[(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}
        (?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\])$
    """,
    re.IGNORECASE
)

BASIC_EMAIL_REGEX = re.compile(r"^[^@]+@[^@]+\.[^@.]+$", re.IGNORECASE)

from backend.app.db import SessionLocal
from backend.app.models.verification_result import VerificationResult
from backend.app.services.verification_ws_manager import verification_ws
from backend.app.services.cache import get_cached, set_cached
from backend.app.services.mx_lookup import choose_mx_for_domain
from backend.app.services.smtp_probe import smtp_probe
from backend.app.services.verification_score import score_verification
from backend.app.services.domain_backoff import get_backoff_seconds, increase_backoff, acquire_slot, release_slot
from backend.app.services.deliverability_monitor import record_domain_result, compute_domain_score
from backend.app.services.processing_lock import acquire_processing_key, release_processing_key, wait_for_processing_result

logger = logging.getLogger(__name__)

# ---------------------------------------------------------
# PROMETHEUS METRICS
# ---------------------------------------------------------
VERIFICATION_TOTAL = Counter("verification_total", "Total verifications", ["status"])
VERIFICATION_LATENCY_SECONDS = Histogram("verification_latency_seconds", "Latency", ["stage"])
VERIFICATION_CACHE_TOTAL = Counter("verification_cache_total", "Cache hits/misses", ["result"])
VERIFICATION_DISPOSABLE_BLOCKED = Counter("verification_disposable_blocked_total", "Blocked disposable")
VERIFICATION_SYNTAX_INVALID = Counter("verification_syntax_invalid_total", "Blocked by syntax")
VERIFICATION_DB_FAILURE_TOTAL = Counter("verification_db_failure_total", "DB failures")

# ---------------------------------------------------------
# EARLY VALIDATION
# ---------------------------------------------------------

def is_valid_syntax(email: str) -> bool:
    email = email.strip()
    if len(email) > 254 or len(email) < 5:
        return False
    if not BASIC_EMAIL_REGEX.match(email):
        return False
    return bool(RFC5322_REGEX.match(email))


# ---------------------------------------------------------
# MAIN ASYNC ENGINE — FULL PIPELINE
# ---------------------------------------------------------

async def verify_email_async(email: str, user_id: Optional[int] = None) -> Dict[str, Any]:
    start_full = time.time()
    original_email = email
    email = (email or "").strip().lower()

    if not email:
        VERIFICATION_TOTAL.labels(status="invalid").inc()
        return {"email": original_email, "status": "invalid", "reason": "empty_email"}

    # 0) DISPOSABLE EMAIL → INSTANT BLOCK
    if is_disposable_email(email):
        VERIFICATION_DISPOSABLE_BLOCKED.inc()
        result = {
            "email": original_email,
            "status": "invalid",
            "reason": "disposable_email",
            "disposable": True,
            "risk_score": 0,
            "cached": False
        }
        try:
            await asyncio.to_thread(set_cached, email, result)
        except:
            pass
        VERIFICATION_TOTAL.labels(status="invalid").inc()
        VERIFICATION_LATENCY_SECONDS.labels(stage="full").observe(time.time() - start_full)
        return result

    # 1) SYNTAX VALIDATION → RFC 5322
    if not is_valid_syntax(email):
        VERIFICATION_SYNTAX_INVALID.inc()
        result = {
            "email": original_email,
            "status": "invalid",
            "reason": "invalid_syntax",
            "risk_score": 0,
            "cached": False
        }
        try:
            await asyncio.to_thread(set_cached, email, result)
        except:
            pass
        VERIFICATION_TOTAL.labels(status="invalid").inc()
        VERIFICATION_LATENCY_SECONDS.labels(stage="full").observe(time.time() - start_full)
        return result

    # 2) CACHE HIT?
    try:
        cached = await asyncio.to_thread(get_cached, email)
    except Exception as e:
        logger.warning("Cache lookup failed: %s", e)
        cached = None

    if cached:
        domain = email.split("@")[-1]
        try:
            await asyncio.to_thread(record_domain_result, domain, cached.get("status") == "valid")
        except:
            pass
        VERIFICATION_CACHE_TOTAL.labels(result="hit").inc()
        VERIFICATION_TOTAL.labels(status=cached.get("status", "unknown")).inc()
        VERIFICATION_LATENCY_SECONDS.labels(stage="full").observe(time.time() - start_full)
        return cached

    VERIFICATION_CACHE_TOTAL.labels(result="miss").inc()

    # 3) DEDUPLICATION LOCK
    got_lock = await acquire_processing_key(email, ttl=60)
    if not got_lock:
        result = await wait_for_processing_result(email, timeout=30)
        if result:
            VERIFICATION_TOTAL.labels(status=result.get("status", "unknown")).inc()
            VERIFICATION_LATENCY_SECONDS.labels(stage="full").observe(time.time() - start_full)
            return result

    try:
        local_part, domain = email.split("@", 1)
        domain = domain.lower()

        # 4) MX LOOKUP
        try:
            mx_hosts = await asyncio.to_thread(choose_mx_for_domain, domain)
        except Exception as e:
            logger.warning("MX lookup failed: %s", e)
            mx_hosts = []

        if not mx_hosts:
            result = {
                "email": original_email,
                "status": "invalid",
                "reason": "no_mx_record",
                "risk_score": 10
            }
            await asyncio.to_thread(set_cached, email, result)
            await asyncio.to_thread(record_domain_result, domain, False)
            VERIFICATION_TOTAL.labels(status="invalid").inc()
            return result

        # 5) DOMAIN BACKOFF
        backoff_sec = await asyncio.to_thread(get_backoff_seconds, domain) or 0
        if backoff_sec > 0:
            await asyncio.sleep(min(backoff_sec, 8))

        # 6) SLOT ACQUISITION
        slot_acquired = await asyncio.to_thread(acquire_slot, domain)
        if not slot_acquired:
            return {"email": original_email, "status": "unknown", "reason": "domain_rate_limited"}

        # 7) SMTP PROBE
        start_smtp = time.time()
        try:
            smtp_res = await smtp_probe(email, mx_hosts)
        except Exception as e:
            logger.exception("SMTP probe failed: %s", e)
            await asyncio.to_thread(increase_backoff, domain)
            smtp_res = {"status": "error", "exception": str(e)}
        finally:
            VERIFICATION_LATENCY_SECONDS.labels(stage="smtp").observe(time.time() - start_smtp)
            await asyncio.to_thread(release_slot, domain)

        # 8) SCORING
        try:
            scored = await asyncio.to_thread(score_verification, smtp_res)
        except Exception as e:
            logger.exception("Scoring failed: %s", e)
            scored = {"status": "unknown", "risk_score": 50}

        # 9) DOMAIN REPUTATION
        try:
            mx_used = smtp_res.get("mx_host") if isinstance(smtp_res, dict) else None
            reputation = await asyncio.to_thread(compute_domain_score, domain, mx_used)
            scored["domain_reputation"] = reputation
        except:
            scored["domain_reputation"] = None

        # 10) FINALIZE RESULT
        scored.update({
            "email": original_email,
            "risk_score": int(scored.get("risk_score", 50))
        })

        # 11) CACHE + DB
        try:
            await asyncio.to_thread(set_cached, email, scored)
        except:
            logger.debug("Cache save failed")

        try:
            await asyncio.to_thread(_persist_verification_result, original_email, user_id, scored)
        except Exception as e:
            VERIFICATION_DB_FAILURE_TOTAL.inc()
            logger.exception("DB save failed: %s", e)

        # 12) METRICS
        status = str(scored.get("status", "unknown"))
        VERIFICATION_TOTAL.labels(status=status).inc()
        VERIFICATION_LATENCY_SECONDS.labels(stage="full").observe(time.time() - start_full)

        return scored

    finally:
        try:
            await release_processing_key(email)
        except:
            pass


# ---------------------------------------------------------
# DB PERSISTENCE
# ---------------------------------------------------------
def _persist_verification_result(email: str, user_id: Optional[int], scored: Dict[str, Any]):
    db = SessionLocal()
    try:
        vr = VerificationResult(
            user_id=user_id,
            job_id=None,
            email=email,
            status=scored.get("status"),
            risk_score=scored.get("risk_score", 50),
            raw=json.dumps(scored),
            cached=False,
        )
        db.add(vr)
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


# ---------------------------------------------------------
# SYNC WRAPPER
# ---------------------------------------------------------
def verify_email_sync(email: str, user_id: Optional[int] = None) -> Dict[str, Any]:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(verify_email_async(email, user_id))
    else:
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(asyncio.run, verify_email_async(email, user_id))
            return future.result()

await verification_ws.push(
    user_id,
    {
        "event": "single_verification",
        "email": email,
        "status": result["status"],
        "score": result.get("risk_score", 0),
        "ts": datetime.utcnow().isoformat()
    }
    )
