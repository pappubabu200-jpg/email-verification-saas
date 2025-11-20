import json
import threading
from typing import Optional, Dict, Any

from backend.app.config import settings

try:
    import redis as _redis  # type: ignore
except Exception:
    _redis = None

# In-memory fallback (thread-safe)
_in_memory_cache: Dict[str, Any] = {}
_lock = threading.Lock()

def cache_key(email: str) -> str:
    return f"verification:result:{email.lower()}"

def get_cached(email: str) -> Optional[Dict]:
    key = cache_key(email)
    # try redis first
    if _redis and settings.REDIS_URL:
        try:
            r = _redis.from_url(settings.REDIS_URL)
            v = r.get(key)
            if v:
                try:
                    return json.loads(v)
                except Exception:
                    return None
        except Exception:
            pass

    # fallback to in-memory
    with _lock:
        val = _in_memory_cache.get(key)
        return val

def set_cached(email: str, payload: Dict, ttl: Optional[int] = None) -> bool:
    key = cache_key(email)
    ttl = ttl or settings.VERIFICATION_CACHE_TTL
    if _redis and settings.REDIS_URL:
        try:
            r = _redis.from_url(settings.REDIS_URL)
            r.setex(key, ttl, json.dumps(payload))
            return True
        except Exception:
            pass

    with _lock:
        _in_memory_cache[key] = payload
    return True
