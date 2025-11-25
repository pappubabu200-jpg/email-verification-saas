# backend/app/services/domain_throttle.py

"""
Domain-level concurrency throttling.
Prevents too many parallel SMTP probes to the SAME domain.
This protects your IP reputation and avoids greylisting.
"""

import logging
import threading

from backend.app.config import settings

logger = logging.getLogger(__name__)

# Try Redis
try:
    import redis
    REDIS = redis.from_url(settings.REDIS_URL)
except Exception:
    REDIS = None

# Fallback in-memory map
_LOCK = threading.Lock()
_SLOTS = {}  # domain → active slot count

# Default concurrency per domain
MAX_SLOTS = int(getattr(settings, "DOMAIN_CONCURRENCY", 3))
SLOT_TTL = int(getattr(settings, "DOMAIN_SLOT_TTL", 30))  # seconds


# ------------------------------------------------------------
# REDIS IMPLEMENTATION
# ------------------------------------------------------------

def _redis_acquire(domain: str) -> bool:
    """
    Tries to increment Redis counter for domain.
    Returns True if slot acquired.
    """
    try:
        key = f"domain:slots:{domain}"
        cur = REDIS.incr(key)

        # On first use, set TTL
        if cur == 1:
            REDIS.expire(key, SLOT_TTL)

        if cur <= MAX_SLOTS:
            return True

        # rollback
        REDIS.decr(key)
        return False

    except Exception as e:
        logger.debug(f"Redis throttle error: {e}")
        return False


def _redis_release(domain: str):
    """Decrements Redis counter for domain."""
    try:
        key = f"domain:slots:{domain}"
        cur = REDIS.decr(key)
        if cur <= 0:
            REDIS.delete(key)
    except Exception:
        pass


# ------------------------------------------------------------
# IN-MEMORY FALLBACK IMPLEMENTATION
# ------------------------------------------------------------

def _mem_acquire(domain: str) -> bool:
    with _LOCK:
        cur = _SLOTS.get(domain, 0)
        if cur >= MAX_SLOTS:
            return False
        _SLOTS[domain] = cur + 1
        return True


def _mem_release(domain: str):
    with _LOCK:
        cur = _SLOTS.get(domain, 0)
        if cur > 0:
            _SLOTS[domain] = cur - 1


# ------------------------------------------------------------
# PUBLIC APIs (USED BY smtp_probe & verification_engine)
# ------------------------------------------------------------

def acquire(domain: str) -> bool:
    """
    Acquire a concurrency slot for the domain.
    Returns True if allowed to continue.
    """
    if not domain:
        return True

    # Redis first
    if REDIS:
        ok = _redis_acquire(domain)
        if ok:
            return True
        return False

    # Fallback
    return _mem_acquire(domain)


def release(domain: str):
    """
    Release a concurrency slot.
    """
    if not domain:
        return

    if REDIS:
        return _redis_release(domain)

    return _mem_release(domain)
