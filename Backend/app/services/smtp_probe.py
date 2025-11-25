# backend/app/services/smtp_probe.py
"""
Robust SMTP probe for email verification.

Design:
 - Try async fast-path with aiosmtplib (if installed)
 - Fallback to sync smtplib in a thread (safer than raw sockets)
 - Wrap blocking helpers (classification, ip-info, spam checks, throttle) in asyncio.to_thread
 - Retries with exponential backoff + jitter
 - Always release domain throttle slot when acquired
 - Minimal logging and no leaking of full PII into logs
"""

import asyncio
import smtplib
import socket
import time
import logging
import random
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# Optional async SMTP
try:
    import aiosmtplib  # type: ignore
    _HAVE_AIOSMTPLIB = True
except Exception:
    _HAVE_AIOSMTPLIB = False

from backend.app.services.ip_intelligence import get_mx_ip_info
from backend.app.services.bounce_classifier import classify_bounce
from backend.app.services.spam_checker import spam_checks
from backend.app.services.domain_throttle import acquire, release
from backend.app.config import settings

# Defaults
DEFAULT_TIMEOUT = 8.0
MAX_RETRIES = 3
BASE_BACKOFF = 2.0  # seconds
JITTER_FACTOR = 0.25  # +/- 25% jitter


# -----------------------------
# ASYNC HELPERS FOR BLOCKING OPS
# -----------------------------
async def _run_in_thread(func, *args, **kwargs):
    return await asyncio.to_thread(func, *args, **kwargs)


# -----------------------------
# ASYNC PROBE (aiosmtplib)
# -----------------------------
async def _async_probe(email: str, mx: str, helo_domain: str, timeout: float = DEFAULT_TIMEOUT) -> Optional[Dict]:
    """
    Async probe using aiosmtplib. Ensures MAIL FROM before RCPT.
    Returns None on failure or a result dict on success.
    """
    try:
        client = aiosmtplib.SMTP(hostname=mx, port=25, timeout=timeout, local_hostname=helo_domain)
        await client.connect()
        try:
            # EHLO/HELO handled by aiosmtplib.connect()
            # Send MAIL FROM then RCPT TO explicitly
            await client.mail("postmaster@" + helo_domain)
            code, msg = await client.rcpt(email)
            # normalize msg
            msg_text = msg.decode() if isinstance(msg, (bytes, bytearray)) else str(msg)
            return {
                "mx_host": mx,
                "rcpt_response_code": int(code) if code is not None else None,
                "rcpt_response_msg": msg_text,
                "smtp_success": 200 <= int(code or 0) < 300,
                "raw": msg_text,
            }
        finally:
            try:
                await client.quit()
            except Exception:
                # ignore quit errors
                pass
    except Exception as e:
        logger.debug("async smtp probe failed for %s on %s: %s", "[REDACTED_EMAIL]", mx, e)
        return None


# -----------------------------
# SYNC PROBE (blocking) - use smtplib for correct SMTP handling
# -----------------------------
def _sync_probe(mx_host: str, email: str, helo_domain: str, timeout: float = DEFAULT_TIMEOUT) -> Optional[Dict]:
    """
    Blocking SMTP probe using smtplib. Runs inside a thread via asyncio.to_thread.
    Returns None on failure or a result dict.
    """
    try:
        # smtplib will do the proper SMTP handshake and handle multiline responses
        with smtplib.SMTP(host=mx_host, port=25, timeout=timeout) as client:
            # Set local hostname for HELO/EHLO
            try:
                client.local_hostname = helo_domain
            except Exception:
                pass

            # optional: client.ehlo_or_helo_if_needed()
            client.ehlo()
            # Use MAIL FROM before RCPT TO
            client.mail("postmaster@" + helo_domain)
            code, msg = client.rcpt(email)
            # msg may be bytes
            if isinstance(msg, (bytes, bytearray)):
                msg = msg.decode(errors="ignore")
            return {
                "mx_host": mx_host,
                "rcpt_response_code": int(code) if code is not None else None,
                "rcpt_response_msg": str(msg),
                "smtp_success": 200 <= int(code or 0) < 300,
                "raw": str(msg),
            }
    except (smtplib.SMTPException, socket.timeout, ConnectionRefusedError, OSError) as e:
        logger.debug("sync smtp probe failed for %s on %s: %s", "[REDACTED_EMAIL]", mx_host, e)
        return None
    except Exception as e:
        logger.exception("unexpected sync probe error for %s on %s: %s", "[REDACTED_EMAIL]", mx_host, e)
        return None


# -----------------------------
# MAIN PROBE FUNCTION (async)
# -----------------------------
async def smtp_probe(email: str, mx_hosts: List[str], helo_domain: str = "localhost") -> Dict[str, any]:
    """
    Unified production SMTP verifier (async wrapper).
    """
    # minimal sanitization for logs
    safe_email_log = "[REDACTED_EMAIL]"

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

    # iterate MX list
    for mx in mx_hosts:
        # domain key for throttling (strip port if present)
        domain = mx.split(":")[0]

        # Acquire domain throttle slot (may be blocking)
        try:
            slot = await _run_in_thread(acquire, domain)
        except Exception as e:
            logger.warning("domain throttle acquire error for %s: %s", domain, e)
            slot = True  # fail-open

        if not slot:
            result["attempts"].append({"mx": mx, "status": "throttled"})
            result["suggested_action"] = "retry"
            continue

        # ensure release is called when we leave this mx
        try:
            # Gather ip info (blocking -> thread)
            try:
                ip_info = await _run_in_thread(get_mx_ip_info, mx)
            except Exception:
                ip_info = None
            result["ip_info"] = ip_info

            # Try retries per MX
            for attempt in range(1, MAX_RETRIES + 1):
                # backoff with jitter
                base = BASE_BACKOFF * (2 ** (attempt - 1))
                jitter = base * JITTER_FACTOR
                backoff = base + random.uniform(-jitter, jitter)
                backoff = max(0.5, backoff)

                attempt_log: Dict = {"mx": mx, "attempt": attempt, "backoff": round(backoff, 2)}

                # Try async fast-path
                async_res = None
                if _HAVE_AIOSMTPLIB:
                    try:
                        async_res = await _async_probe(email, mx, helo_domain, timeout=DEFAULT_TIMEOUT)
                    except Exception:
                        async_res = None

                if async_res:
                    attempt_log.update(async_res)
                    result["attempts"].append(attempt_log)
                    code = async_res.get("rcpt_response_code")
                    msg = async_res.get("rcpt_response_msg")
                else:
                    # sync fallback executed in thread
                    sync_res = await _run_in_thread(_sync_probe, mx, email, helo_domain, DEFAULT_TIMEOUT)
                    if sync_res:
                        attempt_log.update(sync_res)
                        result["attempts"].append(attempt_log)
                        code = sync_res.get("rcpt_response_code")
                        msg = sync_res.get("rcpt_response_msg")
                    else:
                        attempt_log["status"] = "connect_failed"
                        result["attempts"].append(attempt_log)
                        code = None
                        msg = None

                # Decision logic
                if code is not None and 200 <= int(code) < 300:
                    result["final_rcpt_code"] = int(code)
                    result["final_rcpt_response"] = msg
                    result["suggested_action"] = "accept"
                    result["mx_host"] = mx
                    # best-effort classify & spam checks in thread
                    try:
                        bc = await _run_in_thread(classify_bounce, code, msg)
                        sf = await _run_in_thread(spam_checks, email, msg)
                        result["bounce_class"] = bc
                        result["spam_flags"] = sf
                    except Exception:
                        pass
                    break

                # 4xx (temporary) => retry
                if code is not None and 400 <= int(code) < 500:
                    try:
                        bc = await _run_in_thread(classify_bounce, code, msg)
                        sf = await _run_in_thread(spam_checks, email, msg)
                        result["bounce_class"] = bc
                        result["spam_flags"] = sf
                    except Exception:
                        pass
                    if attempt < MAX_RETRIES:
                        await asyncio.sleep(backoff)
                        continue
                    else:
                        result["suggested_action"] = "retry"
                        break

                # 5xx (permanent) => reject
                if code is not None and 500 <= int(code) < 600:
                    try:
                        bc = await _run_in_thread(classify_bounce, code, msg)
                        sf = await _run_in_thread(spam_checks, email, msg)
                        result["bounce_class"] = bc
                        result["spam_flags"] = sf
                    except Exception:
                        pass
                    result["final_rcpt_code"] = int(code)
                    result["final_rcpt_response"] = msg
                    result["suggested_action"] = "reject"
                    break

                # Unknown/no code -> treat as temporary and retry if allowed
                try:
                    bc = await _run_in_thread(classify_bounce, None, msg)
                    sf = await _run_in_thread(spam_checks, email, msg)
                    result["bounce_class"] = bc
                    result["spam_flags"] = sf
                except Exception:
                    pass

                if attempt < MAX_RETRIES:
                    await asyncio.sleep(backoff)
                else:
                    result["suggested_action"] = "retry"

            # end attempts for this mx
            if result["suggested_action"] in ("accept", "reject"):
                break

        finally:
            # Always release throttle slot if acquired
            try:
                await _run_in_thread(release, domain)
            except Exception:
                pass

    # finalize timing
    result["timing_seconds"] = round(time.time() - start, 3)

    # final bounce classification if missing
    if not result.get("bounce_class"):
        try:
            result["bounce_class"] = await _run_in_thread(classify_bounce, result.get("final_rcpt_code"), result.get("final_rcpt_response"))
        except Exception:
            result["bounce_class"] = None

    return result
