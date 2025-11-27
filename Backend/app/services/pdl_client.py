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
# backend/app/services/pdl_client.py
import os
import logging
from typing import Optional, Dict, Any
import httpx
from backend.app.config import settings

logger = logging.getLogger(__name__)

PDL_API_KEY = os.getenv("PDL_API_KEY", getattr(settings, "PDL_API_KEY", None))
PDL_BASE = os.getenv("PDL_BASE_URL", "https://api.peopledatalabs.com/v5")

async def pdl_enrich_email(email: str) -> Optional[Dict[str, Any]]:
    """
    Enrich person by email via PDL enrichment endpoint.
    """
    if not PDL_API_KEY:
        logger.debug("PDL API key not configured")
        return None
    url = f"{PDL_BASE}/person/enrich"
    params = {"email": email}
    headers = {"Accept": "application/json", "Authorization": f"Bearer {PDL_API_KEY}"}
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get(url, headers=headers, params=params)
            r.raise_for_status()
            return r.json()
    except Exception as e:
        logger.debug("PDL enrich failed for %s: %s", email, e)
        return None
# backend/app/services/pdl_client.py

"""
PDL Client (People Data Labs)
Used for:
  ✓ Email enrichment
  ✓ Company domain enrichment
  ✓ Employment history
  ✓ Social links
"""

import os
import logging
import requests

logger = logging.getLogger(__name__)

PDL_API_KEY = os.getenv("PDL_API_KEY", "")
PDL_TIMEOUT = 10


class PDLClient:
    BASE = "https://api.peopledatalabs.com/v5"

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or PDL_API_KEY
        if not self.api_key:
            raise RuntimeError("PDL_API_KEY missing")

    # ------------------------------------------------
    # EMAIL ENRICHMENT
    # ------------------------------------------------
    def fetch_person_by_email(self, email: str) -> dict | None:
        """
        Best endpoint for Decision Maker enrichment.
        GET /person/enrich
        """
        url = f"{self.BASE}/person/enrich"

        params = {
            "api_key": self.api_key,
            "email": email,
        }

        try:
            r = requests.get(url, params=params, timeout=PDL_TIMEOUT)
            if r.status_code == 200:
                data = r.json()
                if data.get("status") == 200:
                    return data.get("data")
            else:
                logger.debug(f"PDL enrich non-200: {r.text}")
        except Exception as e:
            logger.debug(f"PDL enrich error: {e}")

        return None

    # ------------------------------------------------
    # SEARCH PEOPLE BY DOMAIN (optional)
    # ------------------------------------------------
    def search_people_by_domain(self, domain: str, limit: int = 25) -> list[dict]:
        """
        Search for employees of a company domain.
        Useful for DM discovery.
        """
        url = f"{self.BASE}/person/search"

        params = {
            "api_key": self.api_key,
            "query": json.dumps({"work_email": {"$contains": domain}}),
            "size": limit,
        }

        try:
            r = requests.get(url, params=params, timeout=PDL_TIMEOUT)
            if r.status_code == 200:
                return r.json().get("data", [])
        except Exception as e:
            logger.debug(f"PDL search error: {e}")

        return []

