# backend/app/services/processing_lock.py

"""
Processing lock to dedupe concurrent verification requests for the same email.

Prometheus metrics added:
 - processing_lock_acquire_total{result=acquired|contended|error}
 - processing_lock_release_total{result=ok|error}
 - processing_lock_wait_total{result=returned|timeout}
 - processing_lock_latency_seconds{operation=acquire|wait|release}
"""

import time
import logging
from typing import Optional

import redis.asyncio as redis
from backend.app.services.cache import get_cached  # sync; we wrap with to_thread

from prometheus_client import Counter, Histogram

logger = logging.getLogger(__name__)

REDIS_URL = __import__("os").environ.get("REDIS_URL", "redis://localhost:6379/0")
_redis_client: redis.Redis | None = None


# ---------------------------------------------------------
# PROMETHEUS METRICS
# ---------------------------------------------------------
PROCESSING_LOCK_ACQUIRE_TOTAL = Counter(
    "processing_lock_acquire_total",
    "Processing lock acquisition attempts",
    ["result"]  # acquired | contended | error
)

PROCESSING_LOCK_RELEASE_TOTAL = Counter(
    "processing_lock_release_total",
    "Processing lock releases",
    ["result"]  # ok | error
)

PROCESSING_LOCK_WAIT_TOTAL = Counter(
    "processing_lock_wait_total",
    "Wait result for processing lock waiters",
    ["result"]  # returned | timeout
)

PROCESSING_LOCK_LATENCY = Histogram(
    "processing_lock_latency_seconds",
    "Latency of lock operations",
    ["operation"]  # acquire | wait | release
)


# ---------------------------------------------------------
# REDIS CLIENT
# ---------------------------------------------------------
def _get_redis() -> redis.Redis:
    global _redis_client
    if _redis_client is None:
        _redis_client = redis.from_url(REDIS_URL)
    return _redis_client


# ---------------------------------------------------------
# ACQUIRE
# ---------------------------------------------------------
async def acquire_processing_key(email: str, ttl: int = 60) -> bool:
    """
    Attempt to acquire processing lock for `email`.
    Returns True when acquired, False if another worker has the lock.
    """
    r = _get_redis()
    key = f"processing:{email}"

    with PROCESSING_LOCK_LATENCY.labels(operation="acquire").time():
        try:
            ok = await r.set(key, "1", ex=ttl, nx=True)
            if ok:
                PROCESSING_LOCK_ACQUIRE_TOTAL.labels(result="acquired").inc()
            else:
                PROCESSING_LOCK_ACQUIRE_TOTAL.labels(result="contended").inc()
            return bool(ok)

        except Exception as e:
            logger.warning("acquire_processing_key redis error: %s", e)
            PROCESSING_LOCK_ACQUIRE_TOTAL.labels(result="error").inc()
            # fail-open
            return True


# ---------------------------------------------------------
# RELEASE
# ---------------------------------------------------------
async def release_processing_key(email: str):
    r = _get_redis()
    key = f"processing:{email}"

    with PROCESSING_LOCK_LATENCY.labels(operation="release").time():
        try:
            await r.delete(key)
            PROCESSING_LOCK_RELEASE_TOTAL.labels(result="ok").inc()
        except Exception as e:
            PROCESSING_LOCK_RELEASE_TOTAL.labels(result="error").inc()
            logger.warning("release_processing_key redis error: %s", e)


# ---------------------------------------------------------
# WAIT FOR RESULT (DEDUPE)
# ---------------------------------------------------------
async def wait_for_processing_result(
    email: str,
    poll_interval: float = 0.5,
    timeout: float = 30.0
) -> Optional[dict]:
    """
    Poll cache to see if another worker has finished processing.
    Returns cached result or None if timeout reached.
    """
    import asyncio

    start = time.time()
    with PROCESSING_LOCK_LATENCY.labels(operation="wait").time():
        while time.time() - start < timeout:
            try:
                res = await asyncio.to_thread(get_cached, email)
                if res:
                    PROCESSING_LOCK_WAIT_TOTAL.labels(result="returned").inc()
                    return res
            except Exception:
                pass

            await asyncio.sleep(poll_interval)

        PROCESSING_LOCK_WAIT_TOTAL.labels(result="timeout").inc()
        return None
