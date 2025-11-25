# backend/app/services/cache.py

import json
import threading
from typing import Optional, Dict, Any

from backend.app.config import settings

# ---------------------------------------------------------
# Prometheus Metrics
# ---------------------------------------------------------
from prometheus_client import Counter, Histogram

CACHE_OP_TOTAL = Counter(
    "cache_operations_total",
    "Total cache operations performed",
    ["op", "backend", "result"]  # op=get/set, backend=redis/memory, result=hit/miss/ok/error
)

CACHE_LATENCY_SECONDS = Histogram(
    "cache_latency_seconds",
    "Latency for cache operations",
    ["op", "backend"]  # redis or memory
)

# ---------------------------------------------------------
# REDIS INITIALIZATION
# ---------------------------------------------------------
try:
    import redis as _redis  # type: ignore
    REDIS = _redis.from_url(settings.REDIS_URL) if settings.REDIS_URL else None
except Exception:
    REDIS = None  # graceful fallback


# ---------------------------------------------------------
# IN-MEMORY FALLBACK (THREAD-SAFE)
# ---------------------------------------------------------
_in_memory_cache: Dict[str, Any] = {}
_lock = threading.Lock()
_IN_MEMORY_MAX = 10_000  # prevents unbounded RAM usage


def cache_key(email: str) -> str:
    return f"verification:result:{email.lower()}"


# ---------------------------------------------------------
# GET
# ---------------------------------------------------------
def get_cached(email: str) -> Optional[Dict]:
    key = cache_key(email)

    # -----------------------------
    # Redis Fast Path
    # -----------------------------
    if REDIS:
        with CACHE_LATENCY_SECONDS.labels(op="get", backend="redis").time():
            try:
                raw = REDIS.get(key)
                if raw:
                    try:
                        CACHE_OP_TOTAL.labels(op="get", backend="redis", result="hit").inc()
                        return json.loads(raw)
                    except Exception:
                        CACHE_OP_TOTAL.labels(op="get", backend="redis", result="error").inc()
                        return None
                else:
                    CACHE_OP_TOTAL.labels(op="get", backend="redis", result="miss").inc()
            except Exception:
                CACHE_OP_TOTAL.labels(op="get", backend="redis", result="error").inc()

    # -----------------------------
    # In-Memory Fallback
    # -----------------------------
    with CACHE_LATENCY_SECONDS.labels(op="get", backend="memory").time():
        with _lock:
            val = _in_memory_cache.get(key)
            if val is not None:
                CACHE_OP_TOTAL.labels(op="get", backend="memory", result="hit").inc()
            else:
                CACHE_OP_TOTAL.labels(op="get", backend="memory", result="miss").inc()
            return val


# ---------------------------------------------------------
# SET
# ---------------------------------------------------------
def set_cached(email: str, payload: Dict, ttl: Optional[int] = None) -> bool:
    key = cache_key(email)
    ttl = ttl or getattr(settings, "VERIFICATION_CACHE_TTL", 300)

    # -----------------------------
    # Redis Preferred
    # -----------------------------
    if REDIS:
        with CACHE_LATENCY_SECONDS.labels(op="set", backend="redis").time():
            try:
                REDIS.setex(key, ttl, json.dumps(payload))
                CACHE_OP_TOTAL.labels(op="set", backend="redis", result="ok").inc()
                return True
            except Exception:
                CACHE_OP_TOTAL.labels(op="set", backend="redis", result="error").inc()

    # -----------------------------
    # In-Memory Fallback
    # -----------------------------
    with CACHE_LATENCY_SECONDS.labels(op="set", backend="memory").time():
        with _lock:
            if len(_in_memory_cache) >= _IN_MEMORY_MAX:
                # remove oldest inserted key (simple eviction)
                _in_memory_cache.pop(next(iter(_in_memory_cache)), None)
            _in_memory_cache[key] = payload

        CACHE_OP_TOTAL.labels(op="set", backend="memory", result="ok").inc()
        return True
