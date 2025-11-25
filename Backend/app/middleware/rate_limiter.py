# backend/app/middleware/rate_limiter.py
"""
Redis-backed rate limiting middleware.

Behavior:
- Checks limits in this order of identity (first match wins):
    1) API Key (request.state.api_key_row.id)
    2) Team (request.state.team.id or request.state.team_id)
    3) User (request.state.user.id or request.state.api_user_id)
    4) Fallback global (ip-based)
- Maintains two windows:
    - per-minute (short window) -> default 120 req/min
    - per-day (long window) -> default 10000 req/day
- Uses Redis INCR + EXPIRE (atomic enough for fixed windows).
- Returns HTTP 429 with Retry-After header when limit exceeded.
- Does not block requests if Redis is down (fail-open) but logs a warning.
- Reuses app.state.redis if available, otherwise creates its own aioredis client.
"""

import os
import logging
import time
from datetime import datetime
from typing import Optional

from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from fastapi.responses import JSONResponse

logger = logging.getLogger("rate_limiter")
if not logger.handlers:
    # Minimal handler when app logging isn't configured yet
    import sys
    h = logging.StreamHandler(sys.stdout)
    h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logger.addHandler(h)
    logger.setLevel(logging.INFO)

# Defaults (can be overridden by env)
DEFAULT_PER_MINUTE = int(os.getenv("RATE_LIMIT_PER_MINUTE", "120"))      # requests per minute
DEFAULT_PER_DAY = int(os.getenv("RATE_LIMIT_PER_DAY", "10000"))         # requests per day
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
FALLBACK_IP_LIMIT = int(os.getenv("RATE_LIMIT_FALLBACK_IP", "60"))      # per-minute for anonymous IPs


class RateLimiterMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, redis_url: str = REDIS_URL, per_minute: int = DEFAULT_PER_MINUTE, per_day: int = DEFAULT_PER_DAY):
        super().__init__(app)
        self.redis_url = redis_url
        self.per_minute = per_minute
        self.per_day = per_day
        self._redis = None  # lazy init

    async def dispatch(self, request: Request, call_next):
        # Skip trivial endpoints
        path = request.url.path or "/"
        if path.startswith("/health") or path.startswith("/metrics") or path.startswith("/docs") or path.startswith("/openapi.json"):
            return await call_next(request)

        # Resolve identity and limits
        identity, limits = self._resolve_identity_and_limits(request)

        # If identity resolved, perform check
        try:
            redis = await self._get_redis_client(request)
            allowed, retry_after = await self._check_limits(redis, identity, limits)
        except Exception as e:
            # Fail-open: if Redis is down or error occurs, allow the request but log
            logger.warning("Rate limiter error (allowing request): %s", e)
            return await call_next(request)

        if not allowed:
            # Too many requests
            headers = {"Retry-After": str(int(retry_after))}
            return JSONResponse(
                status_code=429,
                content={"detail": "Too Many Requests"},
                headers=headers,
            )

        # Proceed with request
        response = await call_next(request)
        return response

    def _resolve_identity_and_limits(self, request: Request):
        """
        Determine the identity key and limits to apply.

        Returns:
            identity (str): redis-safe prefix for counters (e.g. "ak:123", "team:45", "user:7", "ip:1.2.3.4")
            limits (dict): {"per_minute": int, "per_day": int}
        """
        # Priority: API Key -> Team -> User -> IP fallback
        ak = getattr(getattr(request, "state", None), "api_key_row", None)
        if ak is not None and getattr(ak, "id", None):
            identity = f"ak:{getattr(ak, 'id')}"
            # you may want to fetch per-key limits from DB; fallback to middleware defaults
            per_min = getattr(ak, "per_minute_limit", None) or self.per_minute
            per_day = getattr(ak, "per_day_limit", None) or self.per_day
            return identity, {"per_minute": int(per_min), "per_day": int(per_day)}

        team = getattr(getattr(request, "state", None), "team", None) or getattr(request.state, "team_id", None)
        if team is not None:
            team_id = getattr(team, "id", team) if not isinstance(team, (str, int)) else team
            identity = f"team:{team_id}"
            # Optionally load team-specific limits from env or DB; fallback to defaults
            return identity, {"per_minute": self.per_minute, "per_day": self.per_day}

        user_id = getattr(getattr(request, "state", None), "user", None) and getattr(request.state.user, "id", None) or getattr(request.state, "api_user_id", None)
        if user_id:
            identity = f"user:{user_id}"
            return identity, {"per_minute": self.per_minute, "per_day": self.per_day}

        # Fallback to client IP
        ip = self._client_ip_from_request(request)
        identity = f"ip:{ip}"
        return identity, {"per_minute": FALLBACK_IP_LIMIT, "per_day": self.per_day}

    async def _get_redis_client(self, request: Request):
        """
        Reuse app.state.redis if available, otherwise create a client and attach to app.state.
        """
        # prefer redis already on app.state
        app = request.app
        if hasattr(app.state, "redis") and getattr(app.state, "redis") is not None:
            return app.state.redis

        # lazy-create and store client
        if self._redis is None:
            try:
                import aioredis
                self._redis = aioredis.from_url(self.redis_url)
            except Exception as e:
                logger.warning("Failed to create aioredis client: %s", e)
                raise

        # attach to app.state for reuse across requests (optional)
        try:
            app.state.redis = self._redis
        except Exception:
            pass

        return self._redis

    async def _check_limits(self, redis, identity: str, limits: dict):
        """
        Perform the Redis INCR checks for per-minute and per-day windows.

        Returns:
            (allowed: bool, retry_after_seconds: int)
        """
        per_min = int(limits.get("per_minute", self.per_minute))
        per_day = int(limits.get("per_day", self.per_day))

        # keys with human-friendly TTLs
        now = datetime.utcnow()
        minute_window = now.strftime("%Y%m%d%H%M")   # e.g. 202511251234
        day_window = now.strftime("%Y%m%d")          # e.g. 20251125

        min_key = f"rl:{identity}:min:{minute_window}"
        day_key = f"rl:{identity}:day:{day_window}"

        # Use pipeline / transaction to reduce round trips
        try:
            # aioredis supports multi-exec via pipeline
            pipe = redis.pipeline()
            pipe.incr(min_key, amount=1)
            pipe.incr(day_key, amount=1)
            # want TTLs set only when key is new
            pipe.ttl(min_key)
            pipe.ttl(day_key)
            results = await pipe.execute()
            # results: [min_count, day_count, min_ttl, day_ttl]
            min_count = int(results[0])
            day_count = int(results[1])
            min_ttl = int(results[2]) if results[2] is not None else -2
            day_ttl = int(results[3]) if results[3] is not None else -2

            # ensure TTLs set (set expiry only when key newly created or no ttl)
            if min_ttl < 0:
                # set to seconds until end of minute + small buffer
                secs_left = 60 - now.second + 2
                await redis.expire(min_key, secs_left)
            if day_ttl < 0:
                # seconds until end of day
                secs_left_day = (24 * 3600) - (now.hour * 3600 + now.minute * 60 + now.second) + 10
                await redis.expire(day_key, secs_left_day)

        except Exception as e:
            logger.warning("Redis rate-limit pipeline failed: %s", e)
            # On Redis error: fail-open
            return True, 0

        # check violations
        if min_count > per_min:
            # estimate retry-after as remaining seconds in minute window
            retry_after = 60 - now.second
            return False, retry_after if retry_after > 0 else 1

        if day_count > per_day:
            # estimate retry-after as seconds until next day
            secs_left_day = (24 * 3600) - (now.hour * 3600 + now.minute * 60 + now.second)
            return False, secs_left_day if secs_left_day > 0 else 60 * 60

        return True, 0

    def _client_ip_from_request(self, request: Request) -> str:
        xff = request.headers.get("x-forwarded-for")
        if xff:
            return xff.split(",")[0].strip()
        if request.client:
            return request.client.host
        return "unknown"
