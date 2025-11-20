import dns.resolver
import logging
from typing import List

logger = logging.getLogger(__name__)

def choose_mx_for_domain(domain: str) -> List[str]:
    """
    Return list of MX hosts for a domain sorted by preference.
    Returns empty list on failure.
    """
    if not domain:
        return []
    try:
        answers = dns.resolver.resolve(domain, "MX", lifetime=6.0)
        mx_records = []
        for r in answers:
            # r.preference, r.exchange
            try:
                host = str(r.exchange).rstrip(".")
                pref = int(r.preference)
            except Exception:
                host = str(r).strip(".")
                pref = 100
            mx_records.append((pref, host))
        mx_records.sort(key=lambda x: x[0])
        return [h for _, h in mx_records]
    except Exception as e:
        logger.debug("MX lookup failed for %s: %s", domain, e)
        return []
