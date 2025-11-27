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
# backend/app/services/apollo_client.py
import os
import logging
from typing import Optional, Dict, Any
import httpx
from backend.app.config import settings

logger = logging.getLogger(__name__)

APOLLO_API_KEY = os.getenv("APOLLO_API_KEY", getattr(settings, "APOLLO_API_KEY", None))
APOLLO_BASE = os.getenv("APOLLO_BASE_URL", "https://api.apollo.io/v1")

# Simple async client for searching person data (name/company/email)
async def apollo_search_person(query: str, limit: int = 10) -> Optional[Dict[str, Any]]:
    """
    Query Apollo People/Enrichment endpoints.
    Returns dict or None on failure.
    """
    if not APOLLO_API_KEY:
        logger.debug("Apollo API key not configured")
        return None

    url = f"{APOLLO_BASE}/people/search"
    headers = {"Authorization": f"Bearer {APOLLO_API_KEY}", "Accept": "application/json"}
    params = {"q": query, "per_page": limit}

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get(url, headers=headers, params=params)
            r.raise_for_status()
            return r.json()
    except httpx.HTTPStatusError as e:
        logger.warning("Apollo API status %s: %s", e.response.status_code, e)
    except Exception as e:
        logger.exception("Apollo API error: %s", e)
    return None


async def apollo_enrich_person_by_email(email: str) -> Optional[Dict[str, Any]]:
    """
    Enrich a single person by email if Apollo supports it.
    Returns normalized dict or None.
    """
    if not APOLLO_API_KEY:
        return None
    url = f"{APOLLO_BASE}/people/lookup"
    headers = {"Authorization": f"Bearer {APOLLO_API_KEY}"}
    params = {"email": email}
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            r = await client.get(url, headers=headers, params=params)
            r.raise_for_status()
            return r.json()
    except Exception as e:
        logger.debug("Apollo enrich failed for %s: %s", email, e)
        return None
