# backend/app/services/smtp_probe.py
"""
Robust SMTP probe with:
 - Prometheus metrics
 - Async+sync SMTP paths
 - Async-safe domain throttling
 - Retries + jitter backoff
 - No PII logging
"""

import asyncio
import smtplib
import socket
import time
import logging
import random
from typing import Dict, List, Optional

from prometheus_client import Counter, Histogram, Gauge

from backend.app.services.domain_throttle import (
    acquire_slot_async,
    release_slot_async,
)
from backend.app.services.ip_intelligence import get_mx_ip_info
from backend.app.services.bounce_classifier import classify_bounce
from backend.app.services.spam_checker import spam_checks

logger = logging.getLogger(__name__)

# Optional async SMTP
try:
    import aiosmtplib
    _HAVE_AIOSMTPLIB = True
except Exception:
    _HAVE_AIOSMTPLIB = False

# Defaults
DEFAULT_TIMEOUT = 8.0
MAX_RETRIES = 3
BASE_BACKOFF = 2.0
JITTER_FACTOR = 0.25


# ---------------------------------------------------------
# PROMETHEUS METRICS
# ---------------------------------------------------------
SMTP_PROBE_TOTAL = Counter(
    "smtp_probe_total",
    "Total smtp_probe calls",
    ["domain", "result"]
)

SMTP_PROBE_LATENCY = Histogram(
    "smtp_probe_latency_seconds",
    "SMTP probe execution latency",
    ["domain"]
)

SMTP_PROBE_THROTTLED = Counter(
    "smtp_probe_throttled_total",
    "SMTP probes throttled due to domain concurrency limit",
    ["domain"]
)

SMTP_PROBE_FAILURE = Counter(
    "smtp_probe_failure_total",
    "SMTP probe failures",
    ["domain", "reason"]
)

SMTP_PROBE_IN_PROGRESS = Gauge(
    "smtp_probe_in_progress",
    "Number of in-progress smtp probes",
    ["domain"]
)


# ---------------------------------------------------------
# THREAD HELPER
# ---------------------------------------------------------
async def _run_in_thread(func, *args, **kwargs):
    return await asyncio.to_thread(func, *args, **kwargs)


# ---------------------------------------------------------
# ASYNC SMTP PROBE
# ---------------------------------------------------------
async def _async_probe(email: str, mx: str, helo_domain: str) -> Optional[Dict]:
    try:
        client = aiosmtplib.SMTP(
            hostname=mx, port=25, timeout=DEFAULT_TIMEOUT,
            local_hostname=helo_domain
        )
        await client.connect()
        await client.mail("postmaster@" + helo_domain)
        code, msg = await client.rcpt(email)
        msg = msg.decode() if isinstance(msg, (bytes, bytearray)) else str(msg)

        return {
            "mx_host": mx,
            "rcpt_response_code": int(code) if code else None,
            "rcpt_response_msg": msg,
            "smtp_success": 200 <= int(code or 0) < 300,
            "raw": msg,
        }
    except Exception as e:
        logger.debug("async smtp probe failed for %s on %s: %s", "[REDACTED_EMAIL]", mx, e)
        return None
    finally:
        try:
            await client.quit()
        except Exception:
            pass


# ---------------------------------------------------------
# SYNC SMTP PROBE (RUN IN THREAD)
# ---------------------------------------------------------
def _sync_probe(mx_host: str, email: str, helo_domain: str) -> Optional[Dict]:
    try:
        with smtplib.SMTP(host=mx_host, port=25, timeout=DEFAULT_TIMEOUT) as client:
            client.local_hostname = helo_domain
            client.ehlo()

            client.mail("postmaster@" + helo_domain)
            code, msg = client.rcpt(email)

            msg = msg.decode() if isinstance(msg, (bytes, bytearray)) else str(msg)

            return {
                "mx_host": mx_host,
                "rcpt_response_code": int(code) if code else None,
                "rcpt_response_msg": msg,
                "smtp_success": 200 <= int(code or 0) < 300,
                "raw": msg,
            }

    except Exception as e:
        logger.debug("sync smtp probe failed on %s: %s", mx_host, e)
        return None


# ---------------------------------------------------------
# MAIN PROBE
# ---------------------------------------------------------
async def smtp_probe(email: str, mx_hosts: List[str], helo_domain: str = "localhost") -> Dict[str, any]:
    safe_email = "[REDACTED_EMAIL]"

    result = {
        "email": email,
        "mx_host": None,
        "ip_info": None,
        "attempts": [],
        "final_rcpt_code": None,
        "final_rcpt_response": None,
        "error": None,
        "suggested_action": "reject",
        "bounce_class": None,
        "spam_flags": [],
        "timing_seconds": 0.0,
    }

    if not mx_hosts:
        result["error"] = "no_mx"
        return result

    start = time.time()

    # Loop over MX servers
    for mx in mx_hosts:
        domain = mx.split(":")[0]

        # --------------------------------------
        # PROMETHEUS: mark in-progress
        # --------------------------------------
        SMTP_PROBE_IN_PROGRESS.labels(domain=domain).inc()

        # --------------------------------------
        # Acquire async throttle slot
        # --------------------------------------
        try:
            slot_ok = await acquire_slot_async(domain)
        except Exception as e:
            logger.warning("acquire_slot_async error: %s", e)
            slot_ok = True

        if not slot_ok:
            SMTP_PROBE_THROTTLED.labels(domain=domain).inc()
            result["attempts"].append({"mx": mx, "status": "throttled"})
            result["suggested_action"] = "retry"
            SMTP_PROBE_IN_PROGRESS.labels(domain=domain).dec()
            continue

        try:
            # Get IP reputation
            try:
                ip_info = await _run_in_thread(get_mx_ip_info, mx)
            except Exception:
                ip_info = None
            result["ip_info"] = ip_info

            # RETRIES LOOP
            for attempt in range(1, MAX_RETRIES + 1):
                # backoff + jitter
                base = BASE_BACKOFF * (2 ** (attempt - 1))
                jitter = base * JITTER_FACTOR
                backoff = max(0.5, base + random.uniform(-jitter, jitter))

                attempt_log = {"mx": mx, "attempt": attempt, "backoff": round(backoff, 2)}

                # --------------------------------------
                # PROMETHEUS LATENCY MEASUREMENT
                # --------------------------------------
                with SMTP_PROBE_LATENCY.labels(domain=domain).time():

                    async_res = None
                    if _HAVE_AIOSMTPLIB:
                        async_res = await _async_probe(email, mx, helo_domain)

                    if async_res:
                        attempt_log.update(async_res)
                        result["attempts"].append(attempt_log)
                        code = async_res["rcpt_response_code"]
                        msg = async_res["rcpt_response_msg"]
                    else:
                        sync_res = await _run_in_thread(_sync_probe, mx, email, helo_domain)
                        if sync_res:
                            attempt_log.update(sync_res)
                            result["attempts"].append(attempt_log)
                            code = sync_res["rcpt_response_code"]
                            msg = sync_res["rcpt_response_msg"]
                        else:
                            attempt_log["status"] = "connect_failed"
                            result["attempts"].append(attempt_log)

                            SMTP_PROBE_FAILURE.labels(domain=domain, reason="connect_failed").inc()
                            break

                # --------------------------------------
                # SUCCESS (2xx)
                # --------------------------------------
                if code and 200 <= code < 300:
                    SMTP_PROBE_TOTAL.labels(domain=domain, result="success").inc()

                    result["final_rcpt_code"] = code
                    result["final_rcpt_response"] = msg
                    result["mx_host"] = mx
                    result["suggested_action"] = "accept"

                    try:
                        result["bounce_class"] = await _run_in_thread(classify_bounce, code, msg)
                        result["spam_flags"] = await _run_in_thread(spam_checks, email, msg)
                    except Exception:
                        pass

                    break

                # --------------------------------------
                # 4xx TEMP FAILURE
                # --------------------------------------
                if code and 400 <= code < 500:
                    SMTP_PROBE_FAILURE.labels(domain=domain, reason="4xx").inc()

                    try:
                        result["bounce_class"] = await _run_in_thread(classify_bounce, code, msg)
                        result["spam_flags"] = await _run_in_thread(spam_checks, email, msg)
                    except Exception:
                        pass

                    if attempt < MAX_RETRIES:
                        await asyncio.sleep(backoff)
                        continue
                    else:
                        result["suggested_action"] = "retry"
                        break

                # --------------------------------------
                # 5xx PERMANENT FAILURE
                # --------------------------------------
                if code and 500 <= code < 600:
                    SMTP_PROBE_TOTAL.labels(domain=domain, result="rejected").inc()

                    try:
                        result["bounce_class"] = await _run_in_thread(classify_bounce, code, msg)
                        result["spam_flags"] = await _run_in_thread(spam_checks, email, msg)
                    except Exception:
                        pass

                    result["final_rcpt_code"] = code
                    result["final_rcpt_response"] = msg
                    result["suggested_action"] = "reject"
                    break

                # --------------------------------------
                # UNKNOWN RESPONSE
                # --------------------------------------
                SMTP_PROBE_FAILURE.labels(domain=domain, reason="unknown").inc()

                try:
                    result["bounce_class"] = await _run_in_thread(classify_bounce, None, msg)
                    result["spam_flags"] = await _run_in_thread(spam_checks, email, msg)
                except Exception:
                    pass

                if attempt < MAX_RETRIES:
                    await asyncio.sleep(backoff)
                else:
                    result["suggested_action"] = "retry"

            # end retry loop

            if result["suggested_action"] in ("accept", "reject"):
                break

        finally:
            # --------------------------------------
            # Release throttle + decrement gauge
            # --------------------------------------
            try:
                await release_slot_async(domain)
            except Exception:
                pass

            SMTP_PROBE_IN_PROGRESS.labels(domain=domain).dec()

    result["timing_seconds"] = round(time.time() - start, 3)

    # Final bounce classification if missing
    if not result.get("bounce_class"):
        try:
            result["bounce_class"] = await _run_in_thread(
                classify_bounce,
                result.get("final_rcpt_code"),
                result.get("final_rcpt_response"),
            )
        except Exception:
            result["bounce_class"] = None

    return result
