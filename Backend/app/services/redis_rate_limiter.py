"""
Redis sliding-window rate limiter (Lua script) - production-ready.

Usage:
    from backend.app.services.redis_rate_limiter import RateLimiter
    limiter = RateLimiter(redis_url=settings.REDIS_URL)
    allowed, retry_after = limiter.acquire("limiter:pdl:example.com", limit=5, window_seconds=1)
    if not allowed:
        sleep(retry_after)  # or return 429 to caller

Implementation notes:
- Uses a ZSET (sorted set) per key; members are unique ids, score is timestamp (seconds.millis)
- On each acquire:
    - Remove entries with score < (now - window)
    - Count remaining entries
    - If count + tokens <= limit => ZADD current member(s) and return allowed=1
    - Else return allowed=0 and earliest retry_after estimate (oldest_score + window - now)
- TTL is set on key = window_seconds * 2 to avoid unlimited memory usage
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

logger = logging.getLogger(__name__)

# Lua script: remove old, get count, if allowed add, return allowed and retry_after (0 if allowed)
_SLIDING_WINDOW_LUA = r"""
-- ARGV:
-- 1 = now_ts (as float string)
-- 2 = window_seconds (as float string)
-- 3 = limit (integer)
-- 4 = tokens (integer)
-- 5 = key_ttl_seconds (integer)

local now = tonumber(ARGV[1])
local window = tonumber(ARGV[2])
local limit = tonumber(ARGV[3])
local tokens = tonumber(ARGV[4])
local ttl = tonumber(ARGV[5])

local key = KEYS[1]
local min_score = now - window

-- remove old entries
redis.call('ZREMRANGEBYSCORE', key, '-inf', min_score)

-- current count
local cur = redis.call('ZCARD', key)

if (cur + tokens) <= limit then
    -- allowed: add `tokens` entries with unique members
    for i = 1, tokens do
        local member = tostring(now) .. "-" .. tostring(math.random()) .. "-" .. tostring(i) .. "-" .. tostring(KEYS[1])
        redis.call('ZADD', key, now, member)
    end
    -- set TTL for cleanup
    redis.call('EXPIRE', key, ttl)
    return {1, 0}
else
    -- not allowed: find oldest element's score to compute retry_after
    local oldest = redis.call('ZRANGE', key, 0, 0, 'WITHSCORES')
    local oldest_score = 0
    if oldest and #oldest >= 2 then
        oldest_score = tonumber(oldest[2])
    else
        -- fallback: find min score with zrangebyscore
        local minr = redis.call('ZRANGE', key, 0, 0, 'WITHSCORES')
        if minr and #minr >= 2 then
            oldest_score = tonumber(minr[2])
        else
            oldest_score = min_score -- fallback
        end
    end
    local retry_after = (oldest_score + window) - now
    if retry_after < 0 then
        retry_after = 0
    end
    return {0, retry_after}
end
"""


class RateLimiter:
    def __init__(self, redis_url: str = None):
        if _redis is None:
            raise RuntimeError("redis library not available; pip install redis")
        self.redis_url = redis_url or getattr(settings, "REDIS_URL", None)
        if not self.redis_url:
            raise RuntimeError("REDIS_URL not configured in settings")
        self._client = _redis.from_url(self.redis_url)
        # Register script
        try:
            self._script = self._client.register_script(_SLIDING_WINDOW_LUA)
        except Exception as e:
            # fallback: will use EVAL each time
            logger.debug("Failed to register lua script: %s", e)
            self._script = None

    def _now_ts(self) -> float:
        # use seconds with milliseconds precision
        return time.time()

    def acquire(self, key: str, limit: int, window_seconds: float = 1.0, tokens: int = 1, max_retries: int = 3, retry_backoff: float = 0.1) -> Tuple[bool, float]:
        """
        Try to acquire `tokens` from the limiter.
        Returns (allowed: bool, retry_after_seconds: float)

        If not allowed, retry up to `max_retries` times with exponential backoff (default small).
        """
        now = self._now_ts()
        ttl = max(2, int(window_seconds * 2))  # TTL ensures cleanup of idle keys

        attempt = 0
        while True:
            attempt += 1
            try:
                # prefer registered script
                if self._script:
                    res = self._script(keys=[key], args=[str(now), str(window_seconds), str(int(limit)), str(int(tokens)), str(ttl)])
                    # res is [allowed_int (0/1), retry_after_float]
                    if not res:
                        # fallback unexpected
                        return True, 0.0
                    allowed = bool(int(res[0]))
                    retry_after = float(res[1])
                    if allowed:
                        return True, 0.0
                    else:
                        # not allowed
                        if attempt >= max_retries:
                            return False, float(retry_after)
                        # small sleep then try again
                        sleep_time = float(retry_after) if retry_after and retry_after > 0 else retry_backoff * (2 ** (attempt - 1))
                        time.sleep(sleep_time)
                        now = self._now_ts()
                        continue
                else:
                    # fallback to EVAL (same lua)
                    res = self._client.eval(_SLIDING_WINDOW_LUA, 1, key, str(now), str(window_seconds), str(int(limit)), str(int(tokens)), str(ttl))
                    allowed = bool(int(res[0]))
                    retry_after = float(res[1])
                    if allowed:
                        return True, 0.0
                    else:
                        if attempt >= max_retries:
                            return False, float(retry_after)
                        sleep_time = float(retry_after) if retry_after and retry_after > 0 else retry_backoff * (2 ** (attempt - 1))
                        time.sleep(sleep_time)
                        now = self._now_ts()
                        continue
            except _redis.exceptions.ResponseError as e:
                logger.exception("Redis script error: %s", e)
                # permissive fallback: allow to avoid blocking critical path
                return True, 0.0
            except Exception as e:
                logger.debug("RateLimiter transient error: %s", e)
                # on redis connectivity issues, be permissive
                return True, 0.0

    def get_count(self, key: str, window_seconds: float = 1.0) -> int:
        """
        Return current count in window (best-effort).
        """
        try:
            now = self._now_ts()
            min_score = now - window_seconds
            return int(self._client.zcount(key, min_score, now))
        except Exception:
            return 0
