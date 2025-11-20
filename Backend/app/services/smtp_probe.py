import smtplib
import socket
import logging
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 8.0

def smtp_probe(email: str, mx_hosts: List[str], helo_domain: str = "localhost") -> Dict:
    """
    Attempt a safe SMTP RCPT TO probe against MX hosts.
    We do not send DATA. We perform EHLO/MAIL FROM/RCPT TO and read responses.
    Returns a dictionary with probe details.
    """
    result: Dict = {
        "email": email,
        "mx_host": None,
        "connected": False,
        "rcpt_response": None,
        "rcpt_code": None,
        "error": None,
    }

    if not mx_hosts:
        result["error"] = "no_mx"
        return result

    for host in mx_hosts:
        try:
            # Connect with timeout
            s = smtplib.SMTP(host=host, timeout=DEFAULT_TIMEOUT)
            s.set_debuglevel(0)
            try:
                s.ehlo_or_helo_if_needed()
            except Exception:
                # ignore ehlo errors
                pass

            result["mx_host"] = host
            result["connected"] = True

            # use a safe MAIL FROM
            try:
                code, resp = s.mail("postmaster@" + helo_domain)
            except Exception as e:
                # some servers may refuse or return unusual responses
                logger.debug("MAIL FROM error for %s on %s: %s", email, host, e)
                code, resp = None, str(e)

            try:
                rc, rmsg = s.rcpt(email)
                # rc is numeric code (int) or str depending on smtplib
                try:
                    rc_int = int(rc)
                except Exception:
                    # sometimes rc is '250' string with message
                    rc_int = None
                result["rcpt_code"] = rc_int or rc
                result["rcpt_response"] = rmsg.decode() if isinstance(rmsg, bytes) else str(rmsg)
            except Exception as e:
                result["rcpt_response"] = str(e)
                result["rcpt_code"] = None

            try:
                s.quit()
            except Exception:
                try:
                    s.close()
                except Exception:
                    pass

            # return after first successful MX probe attempt (we want fastest)
            return result
        except (smtplib.SMTPServerDisconnected, smtplib.SMTPConnectError, socket.timeout, ConnectionRefusedError) as exc:
            logger.debug("SMTP connect error (%s): %s", host, exc)
            # try next MX host
            continue
        except Exception as exc:
            logger.debug("SMTP probe unexpected error for host %s: %s", host, exc)
            continue

    # if reached here, no MX worked
    if not result["mx_host"]:
        result["error"] = "all_mx_failed"
    return result

import smtplib
import socket
import time
import logging
from typing import Dict, List, Optional

from backend.app.services.mx_lookup import choose_mx_for_domain
from backend.app.services.domain_throttle import acquire, release
from backend.app.services.ip_intelligence import get_mx_ip_info
from backend.app.services.bounce_classifier import classify_bounce
from backend.app.services.spam_checker import spam_checks
from backend.app.config import settings

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 8.0
MAX_RETRIES = 3
BASE_BACKOFF = 2.0  # seconds


def _safe_connect(host: str, timeout: float = DEFAULT_TIMEOUT) -> Optional[smtplib.SMTP]:
    try:
        s = smtplib.SMTP(host=host, timeout=timeout)
        s.set_debuglevel(0)
        try:
            s.ehlo_or_helo_if_needed()
        except Exception:
            # ignore minor EHLO issues
            pass
        return s
    except Exception as e:
        logger.debug("SMTP connect failed to %s: %s", host, e)
        return None


def smtp_probe(email: str, mx_hosts: List[str], helo_domain: str = "localhost", max_retries: int = MAX_RETRIES) -> Dict:
    """
    Robust SMTP probe with domain-level throttling and exponential backoff.
    Does not send DATA. Performs MAIL FROM + RCPT TO probes and collects full attempt logs.
    Returns a structured dict with:
      - email, mx_host, ip_info, attempts[], final_rcpt_code, final_rcpt_response,
        suggested_action (accept/retry/reject/manual_review), bounce_class, spam_flags
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
        result["suggested_action"] = "reject"
        return result

    start = time.time()
    # Try MX hosts in order
    for mx in mx_hosts:
        domain = mx.split(":")[0]
        # Acquire domain slot (guard concurrent probes)
        if not acquire(domain):
            # domain busy / throttled
            result["attempts"].append({"mx": mx, "status": "throttled"})
            result["suggested_action"] = "retry"
            continue

        try:
            # attach ip info (A records) for reputation scoring
            try:
                ip_info = get_mx_ip_info(mx)
                result["ip_info"] = ip_info
            except Exception:
                result["ip_info"] = None

            attempt_num = 0
            last_rcpt_code = None
            last_rcpt_resp = None

            while attempt_num < max_retries:
                attempt_num += 1
                backoff = BASE_BACKOFF * (2 ** (attempt_num - 1))
                attempt_log = {"mx": mx, "attempt": attempt_num, "backoff": backoff}
                s = _safe_connect(mx, timeout=DEFAULT_TIMEOUT)
                if not s:
                    attempt_log.update({"status": "connect_failed"})
                    result["attempts"].append(attempt_log)
                    # try next MX host
                    break

                try:
                    # MAIL FROM
                    try:
                        mcode, mresp = s.mail("postmaster@" + helo_domain)
                        attempt_log["mail_from_code"] = mcode
                        attempt_log["mail_from_resp"] = mresp.decode() if isinstance(mresp, bytes) else str(mresp)
                    except Exception as e:
                        attempt_log["mail_from_error"] = str(e)

                    # RCPT TO
                    try:
                        rc, rmsg = s.rcpt(email)
                        rc_int = None
                        try:
                            rc_int = int(rc)
                        except Exception:
                            # sometimes rc is string; keep raw
                            rc_int = rc
                        last_rcpt_code = rc_int
                        last_rcpt_resp = rmsg.decode() if isinstance(rmsg, bytes) else str(rmsg)
                        attempt_log["rcpt_code"] = rc_int
                        attempt_log["rcpt_resp"] = last_rcpt_resp
                    except Exception as e:
                        attempt_log["rcpt_error"] = str(e)

                    # close politely
                    try:
                        s.quit()
                    except Exception:
                        try:
                            s.close()
                        except Exception:
                            pass

                    result["attempts"].append(attempt_log)

                    # Decision rules:
                    # 2xx => accept, stop
                    # 4xx => temporary, may retry (greylist)
                    # 5xx => reject (hard bounce)
                    rc_val = None
                    try:
                        rc_val = int(last_rcpt_code) if last_rcpt_code is not None else None
                    except Exception:
                        rc_val = None

                    if rc_val and 200 <= rc_val < 300:
                        result["final_rcpt_code"] = rc_val
                        result["final_rcpt_response"] = last_rcpt_resp
                        result["suggested_action"] = "accept"
                        break
                    if rc_val and 400 <= rc_val < 500:
                        # temporary; implement retry/backoff
                        result["final_rcpt_code"] = rc_val
                        result["final_rcpt_response"] = last_rcpt_resp
                        # classify bounce and spam flags
                        result["bounce_class"] = classify_bounce(rc_val, last_rcpt_resp)
                        result["spam_flags"] = spam_checks(email, last_rcpt_resp)
                        # If we've more retries left, wait backoff and retry
                        if attempt_num < max_retries:
                            time.sleep(backoff)
                            continue
                        else:
                            result["suggested_action"] = "retry"
                            break
                    if rc_val and 500 <= rc_val < 600:
                        result["final_rcpt_code"] = rc_val
                        result["final_rcpt_response"] = last_rcpt_resp
                        result["bounce_class"] = classify_bounce(rc_val, last_rcpt_resp)
                        result["spam_flags"] = spam_checks(email, last_rcpt_resp)
                        result["suggested_action"] = "reject"
                        break

                    # No numeric RCPT code, but have response text
                    if last_rcpt_resp:
                        # classify heuristically
                        bc = classify_bounce(None, last_rcpt_resp)
                        result["bounce_class"] = bc
                        result["spam_flags"] = spam_checks(email, last_rcpt_resp)
                        # if looks temporary -> retry, else reject
                        if "temporary" in (bc or "") or "greylist" in (last_rcpt_resp or "").lower():
                            if attempt_num < max_retries:
                                time.sleep(backoff)
                                continue
                            else:
                                result["suggested_action"] = "retry"
                                break
                        else:
                            result["suggested_action"] = "reject"
                            break

                    # Fallback: nothing conclusive, treat as unknown -> retry
                    if attempt_num < max_retries:
                        time.sleep(backoff)
                        continue
                    else:
                        result["suggested_action"] = "retry"
                        break

                except Exception as exc:
                    attempt_log["error"] = str(exc)
                    result["attempts"].append(attempt_log)
                    # try next MX host
                    break
                finally:
                    # continue outer loop or break controlled above
                    pass

            # If we reached an accept or reject, return
            if result["suggested_action"] in ("accept", "reject"):
                result["mx_host"] = mx
                break
            # else try the next MX host
            result["mx_host"] = mx

        finally:
            # release domain throttle slot
            try:
                release(domain)
            except Exception:
                pass

        # if suggested_action is accept or reject, break early
        if result["suggested_action"] in ("accept", "reject"):
            break

    elapsed = time.time() - start
    result["timing_seconds"] = round(elapsed, 3)

    # Final classification fallback
    if not result.get("bounce_class"):
        result["bounce_class"] = classify_bounce(result.get("final_rcpt_code"), result.get("final_rcpt_response"))
    if not result.get("spam_flags"):
        result["spam_flags"] = spam_checks(email, result.get("final_rcpt_response"))

    return result
