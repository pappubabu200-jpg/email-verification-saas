# backend/app/services/domain_backoff.py

import logging
import time
from backend.app.config import settings

try:
    import redis
    REDIS = redis.from_url(settings.REDIS_URL)
except Exception:
    REDIS = None  # graceful fallback

logger = logging.getLogger(__name__)

# --------------------------------------------
# CONFIG
# --------------------------------------------

DEFAULT_DOMAIN_SLOTS = int(getattr(settings, "DOMAIN_CONCURRENCY", 2))
SLOT_TTL = int(getattr(settings, "DOMAIN_SLOT_TTL", 60))  # seconds
BACKOFF_KEY = "domain:backoff:{}"        # domain → backoff seconds
SLOT_KEY = "domain:slots:{}"             # domain → current active slots


# --------------------------------------------
# DOMAIN CONCURRENCY CONTROL
# --------------------------------------------

def acquire_slot(domain: str) -> bool:
    """
    Redis-based concurrency limiting.
    Allows N parallel SMTP probes per domain.
    """
    if REDIS is None:
        return True  # fallback: allow everything

    try:
        key = SLOT_KEY.format(domain)
        cur = REDIS.incr(key)

        if cur == 1:
            REDIS.expire(key, SLOT_TTL)

        max_slots = int(getattr(settings, "DOMAIN_CONCURRENCY", DEFAULT_DOMAIN_SLOTS))

        if cur <= max_slots:
            return True

        # rejected → rollback
        REDIS.decr(key)
        return False

    except Exception as e:
        logger.debug("acquire_slot error: %s", e)
        return True  # safe fallback


def release_slot(domain: str):
    """
    Release domain slot after SMTP probe.
    """
    if REDIS is None:
        return

    try:
        key = SLOT_KEY.format(domain)
        cur = REDIS.decr(key)
        if cur <= 0:
            REDIS.delete(key)
    except Exception:
        pass


# --------------------------------------------
# DOMAIN BACKOFF SYSTEM
# --------------------------------------------

def get_backoff_seconds(domain: str) -> int:
    """
    Read current backoff window for domain.
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


def increase_backoff(domain: str, base: int = 5, cap: int = 300):
    """
    Exponential backoff:
    Increase domain wait time on temp errors (4xx)
    """
    if REDIS is None:
        return

    try:
        key = BACKOFF_KEY.format(domain)
        cur = REDIS.incr(key)

        ttl = min(cap, base * (2 ** (int(cur) - 1)))
        REDIS.expire(key, ttl)

    except Exception:
        pass


def clear_backoff(domain: str):
    """
    Remove domain backoff entirely.
    """
    if REDIS is None:
        return

    try:
        REDIS.delete(BACKOFF_KEY.format(domain))
    except Exception:
        pass
