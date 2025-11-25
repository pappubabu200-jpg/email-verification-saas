# backend/app/services/decision_cache.py

"""
Decision Maker Cache (Production-Grade)

Enhancements:
- Redis + local in-memory fallback
- TTL support for fallback
- Hash-based cache key (prevents mega-long keys)
- Exception-safe get/set
- Thread-safe local cache (lock controlled)
"""

import json
import time
import hashlib
import threading
from typing import Optional, Dict, Any

from backend.app.config import settings

# ------------------------------
# Redis init (safe)
# ------------------------------
try:
    import redis as _redis
    REDIS = _redis.from_url(settings.REDIS_URL) if settings.REDIS_URL else None
except Exception:
    REDIS = None

# ------------------------------
# Cache Config
# ------------------------------
CACHE_PREFIX = "decision:cache:"
LOCAL_CACHE_TTL = 60 * 60 * 24  # 24h fallback TTL

# thread-safe in-memory fallback
_local_cache: Dict[str, Dict[str, Any]] = {}
_local_lock = threading.Lock()


# ------------------------------
# Key builder (safe for long queries)
# ------------------------------
def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def cache_key_for_query(query: str) -> str:
    # Normalized + hashed to avoid huge Redis keys
    return f"{CACHE_PREFIX}{_hash(query.lower())}"


# ------------------------------
# Safe Get: Redis → local fallback
# ------------------------------
def get_cached(query: str) -> Optional[Dict[str, Any]]:
    key = cache_key_for_query(query)

    # --- REDIS ---
    if REDIS:
        try:
            v = REDIS.get(key)
            if v:
                return json.loads(v)
        except Exception:
            pass  # fallback below

    # --- LOCAL FALLBACK ---
    now = time.time()
    with _local_lock:
        entry = _local_cache.get(key)
        if not entry:
            return None
        if entry["expires_at"] < now:
            # expired
            _local_cache.pop(key, None)
            return None
        return entry["value"]


# ------------------------------
# Safe Set: Redis → local fallback
# ------------------------------
def set_cached(query: str, payload: Dict[str, Any], ttl: int = LOCAL_CACHE_TTL) -> bool:
    key = cache_key_for_query(query)

    # Safe JSON serialization
    try:
        serialized = json.dumps(payload)
    except Exception:
        return False

    # --- REDIS ---
    if REDIS:
        try:
            REDIS.setex(key, ttl, serialized)
            return True
        except Exception:
            pass  # fallback to local

    # --- LOCAL FALLBACK ---
    now = time.time()
    with _local_lock:
        _local_cache[key] = {
            "value": payload,
            "expires_at": now + ttl
        }
    return True
