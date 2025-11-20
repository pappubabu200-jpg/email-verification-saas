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
