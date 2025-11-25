# backend/app/services/redis_rate_limiter.py

"""
Redis sliding-window rate limiter (Lua script) - production-ready with Prometheus metrics.

Metrics included:
 - rate_limiter_attempt_total{result=allowed|denied|error}
 - rate_limiter_latency_seconds{operation=acquire|eval}
 - rate_limiter_retry_total{attempt}
 - rate_limiter_retry_after_seconds
 - rate_limiter_window_count{key}
"""

import time
import uuid
import logging
from typing import Tuple

from backend.app.config import settings

try:
    import redis as _redis
except Exception:
    _redis = None

from prometheus_client import Counter, Histogram, Gauge

logger = logging.getLogger(__name__)

# -------------------------------------------------
# PROMETHEUS METRICS
# -------------------------------------------------
RATE_LIMITER_ATTEMPT_TOTAL = Counter(
    "rate_limiter_attempt_total",
    "Rate limiter allow/deny events",
    ["result"]  # allowed | denied | error
)

RATE_LIMITER_LATENCY = Histogram(
    "rate_limiter_latency_seconds",
    "Latency for rate limiter operations",
    ["operation"]  # acquire|eval
)

RATE_LIMITER_RETRY_TOTAL = Counter(
    "rate_limiter_retry_total",
    "Count of retries attempted by rate limiter",
    ["attempt"]
)

RATE_LIMITER_RETRY_AFTER_SECONDS = Histogram(
    "rate_limiter_retry_after_seconds",
    "Retry-after seconds returned by sliding window limiter"
)

RATE_LIMITER_WINDOW_COUNT = Gauge(
    "rate_limiter_window_count",
    "Count of items currently inside sliding window",
    ["key"]
)

# -------------------------------------------------
# LUA SCRIPT
# -------------------------------------------------
_SLIDING_WINDOW_LUA = r"""
-- ARGV:
-- 1 = now_ts
-- 2 = window_seconds
-- 3 = limit
-- 4 = tokens
-- 5 = key_ttl_seconds

local now = tonumber(ARGV[1])
local window = tonumber(ARGV[2])
local limit = tonumber(ARGV[3])
local tokens = tonumber(ARGV[4])
local ttl = tonumber(ARGV[5])

local key = KEYS[1]
local min_score = now - window

-- remove outdated items
redis.call('ZREMRANGEBYSCORE', key, '-inf', min_score)

local cur = redis.call('ZCARD', key)

-- allowed path
if (cur + tokens) <= limit then
    for i = 1, tokens do
        local member = tostring(now) .. "-" .. tostring(math.random()) .. "-" .. tostring(i)
        redis.call('ZADD', key, now, member)
    end
    redis.call('EXPIRE', key, ttl)
    return {1, 0}
end

-- deny path → compute retry-after
local oldest = redis.call('ZRANGE', key, 0, 0, 'WITHSCORES')
local oldest_score = 0

if oldest and #oldest >= 2 then
    oldest_score = tonumber(oldest[2])
else
    oldest_score = min_score
end

local retry_after = (oldest_score + window) - now
if retry_after < 0 then retry_after = 0 end

return {0, retry_after}
"""


class RateLimiter:
    def __init__(self, redis_url: str = None):
        if _redis is None:
            raise RuntimeError("redis library not installed; run: pip install redis")

        self.redis_url = redis_url or getattr(settings, "REDIS_URL", None)
        if not self.redis_url:
            raise RuntimeError("REDIS_URL not configured")

        self._client = _redis.from_url(self.redis_url)

        # register script if possible
        try:
            self._script = self._client.register_script(_SLIDING_WINDOW_LUA)
        except Exception as e:
            logger.debug("Lua script register failed, using fallback eval: %s", e)
            self._script = None

    def _now_ts(self) -> float:
        return time.time()

    # -----------------------------------------------------
    # ACQUIRE TOKEN
    # -----------------------------------------------------
    def acquire(
        self,
        key: str,
        limit: int,
        window_seconds: float = 1.0,
        tokens: int = 1,
        max_retries: int = 3,
        retry_backoff: float = 0.1
    ) -> Tuple[bool, float]:

        now = self._now_ts()
        ttl = max(2, int(window_seconds * 2))

        attempt = 0

        with RATE_LIMITER_LATENCY.labels(operation="acquire").time():

            while True:
                attempt += 1
                RATE_LIMITER_RETRY_TOTAL.labels(attempt=str(attempt)).inc()

                try:
                    # fast path (evalsha)
                    if self._script:
                        res = self._script(
                            keys=[key],
                            args=[
                                str(now),
                                str(window_seconds),
                                str(int(limit)),
                                str(int(tokens)),
                                str(ttl)
                            ]
                        )
                    else:
                        # fallback: direct EVAL
                        with RATE_LIMITER_LATENCY.labels(operation="eval").time():
                            res = self._client.eval(
                                _SLIDING_WINDOW_LUA,
                                1, key,
                                str(now),
                                str(window_seconds),
                                str(int(limit)),
                                str(int(tokens)),
                                str(ttl)
                            )

                    if not res:
                        RATE_LIMITER_ATTEMPT_TOTAL.labels(result="error").inc()
                        return True, 0.0  # fail-open

                    allowed = bool(int(res[0]))
                    retry_after = float(res[1])

                    # metric for retry-after
                    RATE_LIMITER_RETRY_AFTER_SECONDS.observe(retry_after)

                    # update current window count
                    try:
                        count = self._client.zcount(key, now - window_seconds, now)
                        RATE_LIMITER_WINDOW_COUNT.labels(key=key).set(count)
                    except Exception:
                        pass

                    if allowed:
                        RATE_LIMITER_ATTEMPT_TOTAL.labels(result="allowed").inc()
                        return True, 0.0

                    # denied path
                    RATE_LIMITER_ATTEMPT_TOTAL.labels(result="denied").inc()

                    if attempt >= max_retries:
                        return False, retry_after

                    # sleep using retry_after or exponential backoff
                    sleep_time = retry_after if retry_after > 0 else (retry_backoff * (2 ** (attempt - 1)))
                    time.sleep(sleep_time)

                    # refresh timestamp
                    now = self._now_ts()
                    continue

                except _redis.exceptions.ResponseError as e:
                    logger.error("Redis script error: %s", e)
                    RATE_LIMITER_ATTEMPT_TOTAL.labels(result="error").inc()
                    return True, 0.0

                except Exception as e:
                    logger.debug("RateLimiter transient error: %s", e)
                    RATE_LIMITER_ATTEMPT_TOTAL.labels(result="error").inc()
                    return True, 0.0


    # -----------------------------------------------------
    # GET WINDOW COUNT
    # -----------------------------------------------------
    def get_count(self, key: str, window_seconds: float = 1.0) -> int:
        try:
            now = self._now_ts()
            min_score = now - window_seconds
            count = int(self._client.zcount(key, min_score, now))
            RATE_LIMITER_WINDOW_COUNT.labels(key=key).set(count)
            return count
        except Exception:
            RATE_LIMITER_WINDOW_COUNT.labels(key=key).set(0)
            return 0
