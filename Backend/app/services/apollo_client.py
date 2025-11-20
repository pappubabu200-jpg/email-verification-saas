import time
import requests
import logging
from typing import Dict, Any, List, Optional
from backend.app.config import settings

logger = logging.getLogger(__name__)

APOLLO_BASE = "https://api.apollo.io/v1"  # example base
APOLLO_KEY = getattr(settings, "APOLLO_API_KEY", "") or None

APOLLO_RATE_LIMIT_PER_SEC = 4  # conservative default

def _headers():
    return {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {APOLLO_KEY}"
    }

def apollo_search_people(domain: str, limit: int = 10) -> List[Dict[str, Any]]:
    """
    Query Apollo for people by domain/company. Returns list of people.
    """
    if not APOLLO_KEY:
        logger.debug("Apollo API key not configured")
        return []

    url = f"{APOLLO_BASE}/people/search"
    payload = {
        "q_organization_domains": [domain],
        "page": 1,
        "per_page": limit
    }
    try:
        time.sleep(1.0 / APOLLO_RATE_LIMIT_PER_SEC)
        r = requests.post(url, json=payload, headers=_headers(), timeout=12)
        if r.status_code != 200:
            logger.debug("Apollo returned %s: %s", r.status_code, r.text)
            return []
        data = r.json()
        # Apollo response shapes differ; try common keys
        people = data.get("people") or data.get("results") or data.get("data") or []
        return people
    except Exception as e:
        logger.exception("Apollo search failed: %s", e)
        return []
