# backend/app/services/cache.py

import json
import threading
from typing import Optional, Dict, Any

from backend.app.config import settings

# -----------------------------------------------------------------------------
# REDIS INITIALIZATION
# -----------------------------------------------------------------------------
try:
    import redis as _redis  # type: ignore
    REDIS = _redis.from_url(settings.REDIS_URL) if settings.REDIS_URL else None
except Exception:
    REDIS = None  # graceful fallback


# -----------------------------------------------------------------------------
# IN-MEMORY FALLBACK (THREAD-SAFE)
# -----------------------------------------------------------------------------
_in_memory_cache: Dict[str, Any] = {}
_lock = threading.Lock()
_IN_MEMORY_MAX = 10_000  # prevents unbounded RAM usage


def cache_key(email: str) -> str:
    return f"verification:result:{email.lower()}"


# -----------------------------------------------------------------------------
# GET
# -----------------------------------------------------------------------------
def get_cached(email: str) -> Optional[Dict]:
    key = cache_key(email)

    # ---- Redis Fast Path ----
    if REDIS:
        try:
            raw = REDIS.get(key)
            if raw:
                try:
                    return json.loads(raw)
                except Exception:
                    return None
        except Exception:
            pass

    # ---- In-Memory Fallback ----
    with _lock:
        return _in_memory_cache.get(key)


# -----------------------------------------------------------------------------
# SET
# -----------------------------------------------------------------------------
def set_cached(email: str, payload: Dict, ttl: Optional[int] = None) -> bool:
    key = cache_key(email)
    ttl = ttl or getattr(settings, "VERIFICATION_CACHE_TTL", 300)

    # ---- Redis Preferred ----
    if REDIS:
        try:
            REDIS.setex(key, ttl, json.dumps(payload))
            return True
        except Exception:
            pass

    # ---- In-Memory Fallback ----
    with _lock:
        if len(_in_memory_cache) >= _IN_MEMORY_MAX:
            # remove 1st inserted key (simple eviction)
            _in_memory_cache.pop(next(iter(_in_memory_cache)), None)
        _in_memory_cache[key] = payload

    return True
