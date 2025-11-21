# backend/app/services/domain_backoff.py
import time, logging
from backend.app.config import settings
try:
    import redis
    REDIS = redis.from_url(settings.REDIS_URL)
except Exception:
    REDIS = None

logger = logging.getLogger(__name__)

# Max concurrent probes per domain (default)
DEFAULT_DOMAIN_SLOTS = int(getattr(settings, "DOMAIN_CONCURRENCY", 2))
SLOT_TTL = int(getattr(settings, "DOMAIN_SLOT_TTL", 60))  # seconds
BACKOFF_KEY = "domain:backoff:{}"        # domain -> backoff multiplier record
SLOT_KEY = "domain:slots:{}"             # domain -> integer

def acquire_slot(domain: str) -> bool:
    """
    Atomically increment slot count and enforce limit.
    Returns True if slot granted, False if limit exceeded.
    """
    if REDIS is None:
        return True
    try:
        key = SLOT_KEY.format(domain)
        cur = REDIS.incr(key)
        if cur == 1:
            REDIS.expire(key, SLOT_TTL)
        max_slots = int(getattr(settings, "DOMAIN_CONCURRENCY", DEFAULT_DOMAIN_SLOTS))
        if cur <= max_slots:
            return True
        # exceed -> rollback
        REDIS.decr(key)
        return False
    except Exception as e:
        logger.debug("acquire_slot error: %s", e)
        return True

def release_slot(domain: str):
    if REDIS is None:
        return
    try:
        key = SLOT_KEY.format(domain)
        cur = REDIS.decr(key)
        if cur <= 0:
            REDIS.delete(key)
    except Exception:
        pass

def get_backoff_seconds(domain: str) -> int:
    """
    Get backoff seconds for domain. Uses a multiplier stored in Redis.
    """
    if REDIS is None:
        return 0
    try:
        k = BACKOFF_KEY.format(domain)
        v = REDIS.get(k)
        if not v:
            return 0
        return int(v)
    except Exception:
        return 0

def increase_backoff(domain: str, base: int = 5, cap: int = 300):
    """
    Increase multiplier (exponential-ish).
    """
    if REDIS is None:
        return
    try:
        k = BACKOFF_KEY.format(domain)
        cur = REDIS.incr(k)
        # set TTL so backoff decays after some time
        ttl = min(cap, base * (2 ** (int(cur)-1)))
        REDIS.expire(k, ttl)
    except Exception:
        pass

def clear_backoff(domain: str):
    if REDIS is None:
        return
    try:
        REDIS.delete(BACKOFF_KEY.format(domain))
    except Exception:
        pass
