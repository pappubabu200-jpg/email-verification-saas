
"""
Decision Finder Quota Service (Redis-backed)

Key design:
- Per-user daily quota stored as Redis key: decision:quota:{user_id}:{YYYYMMDD}
- Atomic INCR used to consume quota
- Key TTL set to seconds remaining until next UTC midnight (so it auto-resets)
- Supports simple plans by checking `user.plan` attribute (if present)
- Fallback plan values:
    free  -> 20 searches/day
    pro   -> 200 searches/day
    ent   -> 1000000 (effectively unlimited)
- Raises fast HTTPException(429) on limit hit to integrate with FastAPI
"""

from datetime import datetime, timedelta
from typing import Tuple
import calendar

from fastapi import HTTPException
from backend.app.config import settings

try:
    import redis as _redis
    REDIS = _redis.from_url(settings.REDIS_URL) if getattr(settings, "REDIS_URL", None) else None
except Exception:
    REDIS = None

# Default limits (can be overridden by adding plan attribute to user object)
DEFAULT_PLAN_LIMITS = {
    "free": int(getattr(settings, "DECISION_FINDER_FREE_DAILY", 20)),
    "pro": int(getattr(settings, "DECISION_FINDER_PRO_DAILY", 200)),
    "enterprise": int(getattr(settings, "DECISION_FINDER_ENT_DAILY", 1000000)),
}


def _today_ymd() -> str:
    # Use UTC date; change if you want local timezone
    now = datetime.utcnow()
    return now.strftime("%Y%m%d")


def _seconds_until_utc_midnight() -> int:
    now = datetime.utcnow()
    tomorrow = now + timedelta(days=1)
    midnight = datetime(tomorrow.year, tomorrow.month, tomorrow.day)
    delta = midnight - now
    return int(delta.total_seconds()) + 2  # small safety buffer


def _quota_key(user_id: int, date_ymd: str = None) -> str:
    if date_ymd is None:
        date_ymd = _today_ymd()
    return f"decision:quota:{user_id}:{date_ymd}"


def get_plan_limit_for_user(user_obj) -> int:
    """
    Determine plan limit from user object.
    If user_obj has attribute `plan` (string), map to DEFAULT_PLAN_LIMITS.
    Else fallback to free.
    """
    if not user_obj:
        return DEFAULT_PLAN_LIMITS["free"]
    plan = getattr(user_obj, "plan", None)
    if not plan:
        # maybe you stored in user.profile_plan or stripe plan - try common names
        plan = getattr(user_obj, "plan_name", None) or getattr(user_obj, "stripe_plan", None)
    plan = (plan or "free").lower()
    return DEFAULT_PLAN_LIMITS.get(plan, DEFAULT_PLAN_LIMITS["free"])


def get_usage(user_id: int) -> Tuple[int, int]:
    """
    Return (used, limit) for today's usage for user_id.
    If Redis not available, return (0, limit) to be permissive.
    """
    # Fetch user limit: we can't load user model here (to keep separation),
    # so caller may supply limit; this helper will just read redis count.
    key = _quota_key(user_id)
    if not REDIS:
        # permissive fallback (no quota enforced without Redis)
        return 0, DEFAULT_PLAN_LIMITS["free"]
    try:
        v = REDIS.get(key)
        used = int(v) if v else 0
        # limit unknown here; caller should call get_plan_limit_for_user
        # but we'll return free limit as fallback
        return used, DEFAULT_PLAN_LIMITS["free"]
    except Exception:
        return 0, DEFAULT_PLAN_LIMITS["free"]


def check_and_consume(user_obj, amount: int = 1):
    """
    Atomically try to consume `amount` searches for the user.
    Raises HTTPException(status_code=429) if limit exceeded.
    Returns tuple (used_after, limit)
    """
    # if Redis unavailable, allow (fail-open)
    if not REDIS:
        return 0, get_plan_limit_for_user(user_obj)

    user_id = getattr(user_obj, "id", None)
    if user_id is None:
        # if user object missing, block (safety)
        raise HTTPException(status_code=401, detail="user_required")

    limit = get_plan_limit_for_user(user_obj)
    key = _quota_key(user_id)
    try:
        # INCRBY atomic
        used_after = REDIS.incrby(key, amount)
        # set TTL to midnight if key was just created (when used_after == amount)
        if used_after == amount:
            ttl = _seconds_until_utc_midnight()
            try:
                REDIS.expire(key, ttl)
            except Exception:
                pass
        # if over the limit, rollback increment and raise
        if used_after > limit:
            # decrement back
            try:
                REDIS.decrby(key, amount)
            except Exception:
                pass
            raise HTTPException(status_code=429, detail="decision_finder_quota_exceeded")
        return used_after, limit
    except HTTPException:
        raise
    except Exception:
        # on unexpected errors, be permissive: allow the call
        return 0, limit
