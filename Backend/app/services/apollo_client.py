# backend/app/services/apollo_client.py

import logging
from typing import Dict, Any, List

import httpx

from backend.app.config import settings
from backend.app.services.redis_rate_limiter import AsyncRateLimiter

logger = logging.getLogger(__name__)

# -----------------------------------------
# CONFIG
# -----------------------------------------
APOLLO_BASE = "https://api.apollo.io/v1"
APOLLO_KEY = getattr(settings, "APOLLO_API_KEY", "") or None

APOLLO_RATE_LIMIT_PER_SEC = int(getattr(settings, "APOLLO_RATE_LIMIT_PER_SEC", 4))
APOLLO_RATE_MAX_RETRIES = int(getattr(settings, "APOLLO_RATE_MAX_RETRIES", 5))

# -----------------------------------------
# ASYNC RATE LIMITER
# -----------------------------------------
try:
    limiter = AsyncRateLimiter(redis_url=settings.REDIS_URL)
except Exception as e:
    logger.warning(f"Apollo limiter disabled: {e}")
    limiter = None


# -----------------------------------------
# HEADERS
# -----------------------------------------
def _headers():
    return {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {APOLLO_KEY}"
    }


# -----------------------------------------
# ASYNC APOLLO SEARCH
# -----------------------------------------
async def apollo_search_people(domain: str, limit: int = 10) -> List[Dict[str, Any]]:
    """
    Async call to Apollo.io People Search.
    Includes:
    - async Redis-based rate limiting
    - httpx async HTTP client
    - safe fallbacks
    """
    if not APOLLO_KEY:
        logger.debug("Apollo API key not configured")
        return []

    limiter_key = f"apollo:{domain.lower()}"

    # -----------------------------------------
    # Rate Limit Check
    # -----------------------------------------
    if limiter:
        allowed, retry_after = await limiter.acquire(
            key=limiter_key,
            limit=APOLLO_RATE_LIMIT_PER_SEC,
            window_seconds=1,
            tokens=1,
            max_retries=APOLLO_RATE_MAX_RETRIES,
        )
        if not allowed:
            logger.warning(f"Apollo rate limit hit for {domain}, retry_after={retry_after}")
            return []

    # -----------------------------------------
    # HTTP CALL
    # -----------------------------------------
    url = f"{APOLLO_BASE}/people/search"
    payload = {
        "q_organization_domains": [domain],
        "page": 1,
        "per_page": limit,
    }

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            res = await client.post(url, json=payload, headers=_headers())

        if res.status_code != 200:
            logger.debug(f"Apollo returned {res.status_code}: {res.text}")
            return []

        data = res.json()
        return (
            data.get("people")
            or data.get("results")
            or data.get("data")
            or []
        )

    except Exception as e:
        logger.exception(f"Apollo search failed: {e}")
        return []
