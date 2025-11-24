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

# backend/app/services/domain_backoff.py
import time
import threading

_LOCK = threading.Lock()
_BACKOFF = {}  # domain → {count, until_timestamp}

MAX_BACKOFF_SECONDS = 600  # 10 minutes
INITIAL_BACKOFF = 3        # seconds


def get_backoff_seconds(domain: str) -> int:
    if not domain:
        return 0
    now = time.time()
    with _LOCK:
        info = _BACKOFF.get(domain)
        if not info:
            return 0
        if info["until"] <= now:
            return 0
        return int(info["until"] - now)


def increase_backoff(domain: str):
    if not domain:
        return
    now = time.time()
    with _LOCK:
        old = _BACKOFF.get(domain, {"count": 0, "until": now})
        count = old["count"] + 1
        delay = min(INITIAL_BACKOFF * count, MAX_BACKOFF_SECONDS)
        _BACKOFF[domain] = {"count": count, "until": now + delay}


def clear_backoff(domain: str):
    if not domain:
        return
    with _LOCK:
        if domain in _BACKOFF:
            del _BACKOFF[domain]


# --- Rate-slot system (SMTP concurrency limiter) ---

_SLOTS = {}  # domain → current slots
MAX_SLOTS_PER_DOMAIN = 3


def acquire_slot(domain: str) -> bool:
    if not domain:
        return True
    with _LOCK:
        curr = _SLOTS.get(domain, 0)
        if curr >= MAX_SLOTS_PER_DOMAIN:
            return False
        _SLOTS[domain] = curr + 1
        return True


def release_slot(domain: str):
    if not domain:
        return
    with _LOCK:
        curr = _SLOTS.get(domain, 0)
        if curr > 0:
            _SLOTS[domain] = curr - 1
