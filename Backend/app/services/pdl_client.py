import time
import requests
import logging
from typing import Dict, Any, List, Optional

from backend.app.config import settings
from backend.app.services.redis_rate_limiter import RateLimiter

logger = logging.getLogger(__name__)

PDL_BASE = "https://api.peopledatalabs.com/v5/person"  # v5 example; confirm with PDL docs
PDL_KEY = getattr(settings, "PDL_API_KEY", "") or None

# Conservative per-domain/per-key limit (requests per second)
PDL_RATE_LIMIT_PER_SEC = int(getattr(settings, "PDL_RATE_LIMIT_PER_SEC", 5))
# How many attempts to wait/try when rate limited
PDL_RATE_MAX_RETRIES = int(getattr(settings, "PDL_RATE_MAX_RETRIES", 5))

# create a limiter instance
try:
    _PDL_LIMITER = RateLimiter(redis_url=settings.REDIS_URL)
except Exception as e:
    logger.debug("PDL limiter init failed, rate limiting disabled: %s", e)
    _PDL_LIMITER = None


def _headers():
    return {
        "Content-Type": "application/json",
        "X-Api-Key": PDL_KEY
    }


def pdl_search_by_domain(domain: str, limit: int = 10) -> List[Dict[str, Any]]:
    """
    Query People Data Labs for people at a domain.
    Uses Redis sliding-window limiter per domain key to avoid hitting API limits.
    Returns list of person dicts (raw).
    """
    if not PDL_KEY:
        logger.debug("PDL API key not configured")
        return []

    params = {
        "domain": domain,
        "size": limit
    }

    limiter_key = f"limiter:pdl:{domain.lower()}"
    # Use window 1 second for per-second limit
    if _PDL_LIMITER:
        allowed, retry_after = _PDL_LIMITER.acquire(limiter_key, limit=PDL_RATE_LIMIT_PER_SEC, window_seconds=1.0, tokens=1, max_retries=PDL_RATE_MAX_RETRIES)
        if not allowed:
            logger.warning("PDL rate limit hit for %s - retry_after=%s", domain, retry_after)
            # fail fast and return empty list (could raise HTTPException or sleep longer)
            return []

    try:
        r = requests.get(PDL_BASE, params=params, headers=_headers(), timeout=12)
        if r.status_code != 200:
            logger.debug("PDL returned status %s: %s", r.status_code, r.text)
            return []
        data = r.json()
        people = data.get("data") or data.get("results") or data.get("people") or []
        if isinstance(people, dict):
            people = list(people.values())
        return people
    except Exception as e:
        logger.exception("PDL request failed: %s", e)
        return []
