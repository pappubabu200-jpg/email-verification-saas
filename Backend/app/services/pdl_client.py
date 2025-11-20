import time
import requests
import logging
from typing import Dict, Any, List, Optional
from backend.app.config import settings

logger = logging.getLogger(__name__)

PDL_BASE = "https://api.peopledatalabs.com/v5/person"  # v5 example; confirm with PDL docs
PDL_KEY = getattr(settings, "PDL_API_KEY", "") or None

# Simple per-second limiter using sleep (or integrate redis limiter)
PDL_RATE_LIMIT_PER_SEC = 5  # conservative default; adjust to your plan


def _headers():
    return {
        "Content-Type": "application/json",
        "X-Api-Key": PDL_KEY
    }

def pdl_search_by_domain(domain: str, limit: int = 10) -> List[Dict[str, Any]]:
    """
    Query People Data Labs for people at a domain.
    Returns list of person dicts (raw).
    """
    if not PDL_KEY:
        logger.debug("PDL API key not configured")
        return []

    params = {
        "domain": domain,
        "size": limit
    }
    try:
        time.sleep(1.0 / PDL_RATE_LIMIT_PER_SEC)
        r = requests.get(PDL_BASE, params=params, headers=_headers(), timeout=10)
        if r.status_code != 200:
            logger.debug("PDL returned status %s: %s", r.status_code, r.text)
            return []
        data = r.json()
        # PDL has 'data' or similar wrapper
        people = data.get("data") or data.get("results") or data.get("people") or []
        if isinstance(people, dict):
            # sometimes wrapped
            people = list(people.values())
        return people
    except Exception as e:
        logger.exception("PDL request failed: %s", e)
        return []
