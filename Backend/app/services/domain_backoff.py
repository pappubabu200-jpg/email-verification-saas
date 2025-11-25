"""
Domain-level exponential backoff system (production-ready).

Fixes included:
✔ Correct TTL-based remaining delay
✔ Persistent exponential counter
✔ Redis pipeline atomicity
✔ Proper cleanup on success
"""

import logging
from backend.app.config import settings

try:
    import redis
    REDIS = redis.from_url(settings.REDIS_URL)
except Exception:
    REDIS = None

logger = logging.getLogger(__name__)

# Keys
BACKOFF_VALUE = "domain:backoff:{}"          # stores delay (int)
BACKOFF_COUNT = "domain:backoff:{}:count"    # stores exponential step counter

BASE_BACKOFF = int(getattr(settings, "BACKOFF_BASE", 5))   # default 5 sec
BACKOFF_CAP = int(getattr(settings, "BACKOFF_CAP", 300))   # max 5 min


# -------------------------------------------------------
# READ CURRENT BACKOFF (correct TTL-based)
# -------------------------------------------------------

def get_backoff_seconds(domain: str) -> int:
    if REDIS is None:
        return 0

    try:
        key = BACKOFF_VALUE.format(domain)

        # First read TTL (remaining delay)
        ttl = REDIS.ttl(key)
        if ttl and ttl > 0:
            return ttl

        # Fallback: read stored value
        v = REDIS.get(key)
        if v:
            try:
                return int(v)
            except Exception:
                return 0

        return 0

    except Exception:
        return 0


# -------------------------------------------------------
# INCREASE BACKOFF (exponential)
# -------------------------------------------------------

def increase_backoff(domain: str):
    if REDIS is None:
        return

    try:
        value_key = BACKOFF_VALUE.format(domain)
        count_key = BACKOFF_COUNT.format(domain)

        # Atomically increment count
        pipe = REDIS.pipeline()
        pipe.incr(count_key)
        pipe.expire(count_key, BACKOFF_CAP * 2)
        count, _ = pipe.execute()

        try:
            count = int(count)
        except Exception:
            count = 1

        # Exponential delay
        delay = min(BACKOFF_CAP, BASE_BACKOFF * (2 ** (count - 1)))

        # Set remaining delay + TTL
        REDIS.setex(value_key, delay, delay)

        logger.info(f"[BACKOFF] {domain}: count={count} delay={delay}s")

    except Exception as e:
        logger.debug(f"backoff error: {e}")


# -------------------------------------------------------
# CLEAR BACKOFF (after success)
# -------------------------------------------------------

def clear_backoff(domain: str):
    if REDIS is None:
        return
    try:
        REDIS.delete(BACKOFF_VALUE.format(domain))
        REDIS.delete(BACKOFF_COUNT.format(domain))
        logger.info(f"[BACKOFF] cleared for {domain}")
    except Exception:
        pass
