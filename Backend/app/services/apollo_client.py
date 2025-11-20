import time
import requests
import logging
from typing import Dict, Any, List, Optional

from backend.app.config import settings
from backend.app.services.redis_rate_limiter import RateLimiter

logger = logging.getLogger(__name__)

APOLLO_BASE = "https://api.apollo.io/v1"  # example base
APOLLO_KEY = getattr(settings, "APOLLO_API_KEY", "") or None

APOLLO_RATE_LIMIT_PER_SEC = int(getattr(settings, "APOLLO_RATE_LIMIT_PER_SEC", 4))
APOLLO_RATE_MAX_RETRIES = int(getattr(settings, "APOLLO_RATE_MAX_RETRIES", 5))

try:
    _APOLLO_LIMITER = RateLimiter(redis_url=settings.REDIS_URL)
except Exception as e:
    logger.debug("Apollo limiter init failed, rate limiting disabled: %s", e)
    _APOLLO_LIMITER = None


def _headers():
    return {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {APOLLO_KEY}"
    }


def apollo_search_people(domain: str, limit: int = 10) -> List[Dict[str, Any]]:
    """
    Query Apollo for people by domain/company. Returns list of people.
    Uses Redis sliding-window limiter.
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

    limiter_key = f"limiter:apollo:{domain.lower()}"
    if _APOLLO_LIMITER:
        allowed, retry_after = _APOLLO_LIMITER.acquire(limiter_key, limit=APOLLO_RATE_LIMIT_PER_SEC, window_seconds=1.0, tokens=1, max_retries=APOLLO_RATE_MAX_RETRIES)
        if not allowed:
            logger.warning("Apollo rate limit hit for %s - retry_after=%s", domain, retry_after)
            return []

    try:
        r = requests.post(url, json=payload, headers=_headers(), timeout=15)
        if r.status_code != 200:
            logger.debug("Apollo returned %s: %s", r.status_code, r.text)
            return []
        data = r.json()
        people = data.get("people") or data.get("results") or data.get("data") or []
        return people
    except Exception as e:
        logger.exception("Apollo search failed: %s", e)
        return []
