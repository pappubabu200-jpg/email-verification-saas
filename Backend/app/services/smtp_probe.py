import asyncio
import smtplib
import socket
import time
import logging
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# Optional async SMTP
try:
    import aiosmtplib
    _HAVE_AIOSMTPLIB = True
except Exception:
    _HAVE_AIOSMTPLIB = False

# Internal services
from backend.app.services.ip_intelligence import get_mx_ip_info
from backend.app.services.bounce_classifier import classify_bounce
from backend.app.services.spam_checker import spam_checks
from backend.app.services.domain_throttle import acquire, release
from backend.app.config import settings


# Defaults
DEFAULT_TIMEOUT = 8.0
MAX_RETRIES = 3
BASE_BACKOFF = 2.0  # seconds


# -----------------------------
# OPTIONAL ASYNC SMTP PROBE
# -----------------------------
async def _async_probe(email: str, mx: str, timeout: float = DEFAULT_TIMEOUT) -> Optional[Dict]:
    """Try using aiosmtplib if available."""
    try:
        client = aiosmtplib.SMTP(hostname=mx, port=25, timeout=timeout)
        await client.connect()
        await client.ehlo()

        code, msg = await client.rcpt(email)
        msg = msg.decode() if isinstance(msg, bytes) else str(msg)

        try:
            await client.quit()
        except Exception:
            pass

        return {
            "mx_host": mx,
            "rcpt_response_code": int(code),
            "rcpt_response_msg": msg,
            "smtp_success": 200 <= int(code) < 300,
            "raw": msg
        }
    except Exception as e:
        logger.debug("async smtp probe failed for %s on %s: %s", email, mx, e)
        return None


# -----------------------------
# SYNC SMTP PROBE (MAIN ENGINE)
# -----------------------------
def _sync_probe(mx_host: str, email: str) -> Optional[Dict]:
    """Raw synchronous RCPT TO using smtplib and socket."""
    try:
        with socket.create_connection((mx_host, 25), timeout=DEFAULT_TIMEOUT) as sock:
            sf = sock.makefile("rb")

            # Read banner
            sf.readline()

            # EHLO
            sock.sendall(b"EHLO example.com\r\n")
            for _ in range(5):
                l = sf.readline().decode(errors="ignore")
                if not l or l.startswith("250 "):
                    break

            # MAIL FROM
            sock.sendall(f"MAIL FROM:<postmaster@{mx_host}>\r\n".encode())
            sf.readline()

            # RCPT TO
            sock.sendall(f"RCPT TO:<{email}>\r\n".encode())
            rc_line = sf.readline().decode(errors="ignore").strip()
            parts = rc_line.split(" ", 1)
            code = int(parts[0]) if parts and parts[0].isdigit() else None
            msg = parts[1] if len(parts) > 1 else rc_line

            try:
                sock.sendall(b"QUIT\r\n")
            except Exception:
                pass

            return {
                "mx_host": mx_host,
                "rcpt_response_code": code,
                "rcpt_response_msg": msg,
                "smtp_success": 200 <= (code or 0) < 300,
                "raw": rc_line,
            }

    except Exception as e:
        logger.debug("sync smtp probe failed for %s on %s: %s", email, mx_host, e)
        return None


# -----------------------------
# FINAL PRODUCTION SMTP PROBE
# -----------------------------
async def smtp_probe(email: str, mx_hosts: List[str], helo_domain: str = "localhost") -> Dict[str, any]:
    """
    Unified production SMTP verifier (async wrapper around sync engine).
    Handles:
      ✔ async aiosmtplib fast path
      ✔ sync fallback
      ✔ retries + backoff
      ✔ domain throttle
      ✔ bounce + spam analysis
      ✔ IP reputation
      ✔ full logs
    """

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

    # Try MX servers in priority order
    for mx in mx_hosts:
        domain = mx.split(":")[0]

        # Acquire domain throttle slot
        if not acquire(domain):
            result["attempts"].append({"mx": mx, "status": "throttled"})
            result["suggested_action"] = "retry"
            continue

        try:
            # IP reputation info
            try:
                result["ip_info"] = get_mx_ip_info(mx)
            except Exception:
                result["ip_info"] = None

            # Retries loop
            attempt = 0
            for attempt in range(1, MAX_RETRIES + 1):
                backoff = BASE_BACKOFF * (2 ** (attempt - 1))
                attempt_log = {"mx": mx, "attempt": attempt, "backoff": backoff}

                # --- Try async aiosmtplib first ---
                if _HAVE_AIOSMTPLIB:
                    async_res = await _async_probe(email, mx)
                    if async_res:
                        attempt_log["async"] = True
                        attempt_log.update(async_res)
                        result["attempts"].append(attempt_log)
                        code = async_res["rcpt_response_code"]
                        msg = async_res["rcpt_response_msg"]
                    else:
                        async_res = None

                # --- If async failed OR not installed → sync fallback ---
                if not _HAVE_AIOSMTPLIB or not async_res:
                    sync_res = await asyncio.to_thread(_sync_probe, mx, email)
                    attempt_log["async"] = False
                    if sync_res:
                        attempt_log.update(sync_res)
                        result["attempts"].append(attempt_log)
                        code = sync_res["rcpt_response_code"]
                        msg = sync_res["rcpt_response_msg"]
                    else:
                        attempt_log["status"] = "connect_failed"
                        result["attempts"].append(attempt_log)
                        break

                # Decision logic
                if code and 200 <= code < 300:
                    result["final_rcpt_code"] = code
                    result["final_rcpt_response"] = msg
                    result["suggested_action"] = "accept"
                    result["mx_host"] = mx
                    break

                if code and 400 <= code < 500:
                    result["final_rcpt_code"] = code
                    result["final_rcpt_response"] = msg
                    result["bounce_class"] = classify_bounce(code, msg)
                    result["spam_flags"] = spam_checks(email, msg)
                    if attempt < MAX_RETRIES:
                        await asyncio.sleep(backoff)
                        continue
                    else:
                        result["suggested_action"] = "retry"
                        break

                if code and 500 <= code < 600:
                    result["final_rcpt_code"] = code
                    result["final_rcpt_response"] = msg
                    result["bounce_class"] = classify_bounce(code, msg)
                    result["spam_flags"] = spam_checks(email, msg)
                    result["suggested_action"] = "reject"
                    break

                # Unknown / No code
                bc = classify_bounce(None, msg)
                result["bounce_class"] = bc
                result["spam_flags"] = spam_checks(email, msg)

                if attempt < MAX_RETRIES:
                    await asyncio.sleep(backoff)
                else:
                    result["suggested_action"] = "retry"

            # End of retry loop
            if result["suggested_action"] in ("accept", "reject"):
                break

        finally:
            try:
                release(domain)
            except Exception:
                pass

    # Finalize timing
    result["timing_seconds"] = round(time.time() - start, 3)

    # Final fallback classification
    if not result["bounce_class"]:
        result["bounce_class"] = classify_bounce(
            result.get("final_rcpt_code"),
            result.get("final_rcpt_response")
        )

    return result
