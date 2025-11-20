import json
import time
from typing import Optional, Dict, Any
from backend.app.config import settings

try:
    import redis as _redis
    REDIS = _redis.from_url(settings.REDIS_URL) if settings.REDIS_URL else None
except Exception:
    REDIS = None

CACHE_PREFIX = "decision:cache:"

def cache_key_for_query(query: str) -> str:
    return f"{CACHE_PREFIX}{query.lower()}"

def get_cached(query: str) -> Optional[Dict[str, Any]]:
    if not REDIS:
        return None
    try:
        v = REDIS.get(cache_key_for_query(query))
        if not v:
            return None
        return json.loads(v)
    except Exception:
        return None

def set_cached(query: str, payload: Dict[str, Any], ttl: int = 60 * 60 * 24):
    # default 24 hours
    if not REDIS:
        return False
    try:
        REDIS.setex(cache_key_for_query(query), ttl, json.dumps(payload))
        return True
    except Exception:
        return False
