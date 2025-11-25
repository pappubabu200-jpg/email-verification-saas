# backend/app/services/processing_lock.py
"""
Processing lock to dedupe concurrent verification requests for the same email.

API:
 - await acquire_processing_key(email, ttl=60) -> True if lock acquired
 - await release_processing_key(email) -> release lock (best-effort)
 - await wait_for_processing_result(email, poll_interval=0.5, timeout=30) -> returns cached result or None

Internals:
 - Uses Redis SET NX with TTL to claim processing token.
 - The verification pipeline should:
     1) Try to read cached result (fast)
     2) If not cached, try to acquire processing key:
         - If acquired: proceed to compute (and set cache), then release key
         - If not acquired: wait for cache update by polling (wait_for_processing_result)
"""

import time
import logging
from typing import Optional

import redis.asyncio as redis
from backend.app.services.cache import get_cached  # reuse existing cache API (may be sync; wrap accordingly)

logger = logging.getLogger(__name__)
REDIS_URL = __import__("os").environ.get("REDIS_URL", "redis://localhost:6379/0")
_redis_client: redis.Redis | None = None


def _get_redis() -> redis.Redis:
    global _redis_client
    if _redis_client is None:
        _redis_client = redis.from_url(REDIS_URL)
    return _redis_client


async def acquire_processing_key(email: str, ttl: int = 60) -> bool:
    """
    Attempt to acquire processing lock for `email`. Returns True when acquired.
    """
    r = _get_redis()
    key = f"processing:{email}"
    try:
        # SET key value NX EX ttl
        ok = await r.set(key, "1", ex=ttl, nx=True)
        return bool(ok)
    except Exception as e:
        logger.warning("acquire_processing_key redis error: %s", e)
        # Fail-open: if Redis fails, allow processing to continue (avoid false rejections)
        return True


async def release_processing_key(email: str):
    r = _get_redis()
    key = f"processing:{email}"
    try:
        await r.delete(key)
    except Exception as e:
        logger.warning("release_processing_key redis error: %s", e)


async def wait_for_processing_result(email: str, poll_interval: float = 0.5, timeout: float = 30.0) -> Optional[dict]:
    """
    Poll cache for a result produced by the original processing worker.
    Returns cached result dict when available, else None on timeout.
    """
    start = time.time()
    while time.time() - start < timeout:
        try:
            # get_cached might be sync — wrap in thread if needed
            res = await __import__("asyncio").to_thread(get_cached, email)
            if res:
                return res
        except Exception:
            pass
        await asyncio.sleep(poll_interval)
    return None
