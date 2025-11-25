# backend/app/services/domain_backoff.py

"""
Domain-level exponential backoff system.
Used when an SMTP server returns temporary (4xx) errors.
Prevents hammering a throttled domain.
"""

import logging
import time
from backend.app.config import settings

try:
    import redis
    REDIS = redis.from_url(settings.REDIS_URL)
except Exception:
    REDIS = None

logger = logging.getLogger(__name__)

# ---------------------------
# CONFIG
# ---------------------------
BACKOFF_KEY = "domain:backoff:{}"
BASE_BACKOFF = int(getattr(settings, "BACKOFF_BASE", 5))     # seconds
BACKOFF_CAP = int(getattr(settings, "BACKOFF_CAP", 300))     # max 5 minutes


# ---------------------------
# READ CURRENT BACKOFF
# ---------------------------

def get_backoff_seconds(domain: str) -> int:
    """
    Return the remaining backoff time for the domain.
    Redis: store TTL as actual delay.
    Memory fallback: always returns 0 (disabled).
    """
    if REDIS is None:
        return 0

    try:
        v = REDIS.get(BACKOFF_KEY.format(domain))
        if not v:
            return 0
        return int(v)
    except Exception:
        return 0


# ---------------------------
# INCREASE BACKOFF
# ---------------------------

def increase_backoff(domain: str):
    """
    Increase backoff duration using exponential growth.
    Only used on temporary/greylist/timeout errors.
    """
    if REDIS is None:
        return

    try:
        key = BACKOFF_KEY.format(domain)
        cur = REDIS.incr(key)

        # Exponential delay
        delay = min(BACKOFF_CAP, BASE_BACKOFF * (2 ** (int(cur) - 1)))

        # Expire after delay seconds
        REDIS.expire(key, delay)

    except Exception:
        pass


# ---------------------------
# CLEAR BACKOFF
# ---------------------------

def clear_backoff(domain: str):
    """
    Reset backoff completely after successful validations.
    """
    if REDIS is None:
        return

    try:
        REDIS.delete(BACKOFF_KEY.format(domain))
    except Exception:
        pass
