# backend/app/services/domain_throttle.py
"""
Domain-level throttle / slot manager.

Purpose
-------
- Limit concurrent SMTP probes (or other domain-bound work) per-domain.
- Prefer Redis-backed counters (cross-process). Fall back to in-memory thread-safe counters
  for single-process or when Redis is unavailable.
- Provide `acquire(domain) -> bool` and `release(domain) -> None`.
- Provide `domain_slot(domain)` context manager for safe usage in `with` blocks.
- Designed to be safe: never raise on transient Redis failures (fail-open).

Configuration (via backend.app.config.settings)
- DOMAIN_CONCURRENCY: max concurrent slots per domain (default: 2)
- DOMAIN_SLOT_TTL: TTL in seconds for Redis slot key (default: 60)

Notes
-----
- Callers MUST call `release(domain)` in `finally` blocks if `acquire` returned True.
- When using context manager, release is automatic.
"""

from __future__ import annotations

import logging
import threading
import time
from contextlib import contextmanager
from typing import Optional

from backend.app.config import settings

logger = logging.getLogger(__name__)

# Attempt to initialize Redis. If unavailable, we'll use the in-memory fallback.
try:
    import redis as _redis  # type: ignore
    REDIS = _redis.from_url(getattr(settings, "REDIS_URL", "") or "")
except Exception:
    REDIS = None

# Config
DEFAULT_DOMAIN_SLOTS = int(getattr(settings, "DOMAIN_CONCURRENCY", 2))
SLOT_TTL = int(getattr(settings, "DOMAIN_SLOT_TTL", 60))  # seconds
SLOT_KEY_TPL = "domain:slots:{}"  # format(domain)
_LOCK = threading.Lock()

# In-memory fallback structures: domain -> count
_in_memory_slots: dict[str, int] = {}


# Optional metrics hooks (no-op by default). If you have Prometheus, replace them.
def metrics_increment(domain: str) -> None:
    # Implement metrics increment here if desired (e.g., prometheus counter)
    return None


def metrics_decrement(domain: str) -> None:
    # Implement metrics decrement here if desired (e.g., prometheus counter)
    return None


def _redis_acquire(domain: str, max_slots: int, slot_ttl: int) -> bool:
    """
    Attempt to atomically increment a Redis counter for the domain and set an expiry.
    Returns True if the new count is <= max_slots else rolls back and returns False.

    On Redis errors, returns True (fail-open).
    """
    if not REDIS:
        return True

    try:
        key = SLOT_KEY_TPL.format(domain)
        # INCR returns the new value after increment
        new_val = REDIS.incr(key)
        if new_val == 1:
            # first time key created; set TTL
            try:
                REDIS.expire(key, slot_ttl)
            except Exception:
                # TTL set failure is non-fatal
                logger.debug("Domain throttle: failed to set expire on key %s", key)

        if new_val <= max_slots:
            # success
            metrics_increment(domain)
            return True

        # exceeded -> rollback
        try:
            REDIS.decr(key)
        except Exception:
            # If rollback fails, log and still treat as failure (but don't raise)
            logger.debug("Domain throttle: rollback decrement failed for key %s", key)

        return False

    except Exception as exc:
        # On transient Redis errors we intentionally allow the operation to continue (fail-open).
        logger.debug("Domain throttle: redis acquire error for %s: %s", domain, exc)
        return True


def _redis_release(domain: str) -> None:
    """
    Decrement Redis slot count for domain; delete key if <= 0.
    Silently ignore errors (fail-safe).
    """
    if not REDIS:
        return

    try:
        key = SLOT_KEY_TPL.format(domain)
        new_val = REDIS.decr(key)
        try:
            new_val_int = int(new_val)
        except Exception:
            new_val_int = None

        # If counter is zero or negative, remove the key
        if new_val_int is None or new_val_int <= 0:
            try:
                REDIS.delete(key)
            except Exception:
                pass

        metrics_decrement(domain)

    except Exception as exc:
        logger.debug("Domain throttle: redis release error for %s: %s", domain, exc)


def _mem_acquire(domain: str, max_slots: int) -> bool:
    """
    Thread-safe in-process fallback.
    """
    with _LOCK:
        cur = _in_memory_slots.get(domain, 0)
        if cur >= max_slots:
            return False
        _in_memory_slots[domain] = cur + 1
    metrics_increment(domain)
    return True


def _mem_release(domain: str) -> None:
    with _LOCK:
        cur = _in_memory_slots.get(domain, 0)
        if cur <= 1:
            # delete key for cleanliness
            if domain in _in_memory_slots:
                del _in_memory_slots[domain]
        else:
            _in_memory_slots[domain] = cur - 1
    metrics_decrement(domain)


def acquire(domain: Optional[str]) -> bool:
    """
    Acquire a domain slot. Returns True if slot granted, False if domain is overloaded.

    If domain is None/empty, returns True (no domain-level limit).

    Always safe to call; will not raise on transient errors.
    """
    if not domain:
        return True

    try:
        max_slots = int(getattr(settings, "DOMAIN_CONCURRENCY", DEFAULT_DOMAIN_SLOTS))
        slot_ttl = int(getattr(settings, "DOMAIN_SLOT_TTL", SLOT_TTL))
    except Exception:
        max_slots = DEFAULT_DOMAIN_SLOTS
        slot_ttl = SLOT_TTL

    # Prefer Redis-backed
    if REDIS:
        return _redis_acquire(domain, max_slots, slot_ttl)

    # Fallback to in-memory
    return _mem_acquire(domain, max_slots)


def release(domain: Optional[str]) -> None:
    """
    Release a previously acquired slot for domain. Safe to call even if acquire returned False,
    and safe on transient errors.
    """
    if not domain:
        return

    if REDIS:
        _redis_release(domain)
        return

    _mem_release(domain)


@contextmanager
def domain_slot(domain: Optional[str], wait: bool = False, retry_delay: float = 0.2, max_retries: int = 5):
    """
    Context manager that acquires a domain slot on entry and releases on exit.

    Parameters
    ----------
    domain: str | None
        Domain to acquire a slot for.
    wait: bool
        If True, the context manager will attempt retries until it acquires a slot (with exponential backoff).
        If False, it will return immediately (raise RuntimeError via context if not acquired).
    retry_delay: float
        Initial retry delay in seconds (exponential backoff).
    max_retries: int
        Number of retries when wait=True. Final attempt counts as well.

    Usage:
        with domain_slot(domain):
            # do SMTP probe
    """
    if not domain:
        # Nothing to do — just yield
        yield
        return

    acquired = False
    if wait:
        attempt = 0
        delay = float(retry_delay)
        while attempt < max_retries:
            attempt += 1
            acquired = acquire(domain)
            if acquired:
                break
            time.sleep(delay)
            delay = min(delay * 2.0, 5.0)
    else:
        acquired = acquire(domain)

    try:
        if not acquired:
            # Caller expected immediate acquisition; raise to signal throttle
            raise RuntimeError(f"domain_slots_full: {domain}")
        yield
    finally:
        if acquired:
            try:
                release(domain)
            except Exception as e:
                logger.debug("domain_slot: release failed for %s: %s", domain, e)


# Helper: check current slots (useful for admin / debugging)
def current_slots(domain: str) -> int:
    """
    Return approximate current slot count for domain.
    If Redis is available this returns the Redis counter (or 0).
    Otherwise returns the in-memory count.
    """
    if not domain:
        return 0

    if REDIS:
        try:
            key = SLOT_KEY_TPL.format(domain)
            v = REDIS.get(key)
            return int(v) if v else 0
        except Exception:
            return 0

    with _LOCK:
        return int(_in_memory_slots.get(domain, 0))
