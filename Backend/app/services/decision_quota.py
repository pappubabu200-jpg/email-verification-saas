"""
Decision Finder Quota Service (Redis-backed)

Implements per-user daily quota using Redis atomic INCRBY.

Features:
- Per-user, per-day key: decision:quota:{user_id}:{YYYYMMDD}
- Auto-reset at next UTC midnight (TTL)
- Plan-based limits: free → 20/day, pro → 200/day, enterprise → unlimited
- Provides:
    - get_usage(user_id)
    - check_and_consume(user_obj, amount=1)
- Fail-open if Redis unavailable (prevents blocking core functionality)
"""

from datetime import datetime, timedelta
from typing import Tuple
from fastapi import HTTPException

from backend.app.config import settings

# ----------------------------------------
# Redis Setup
# ----------------------------------------
try:
    import redis as _redis
    REDIS = _redis.from_url(settings.REDIS_URL) if settings.REDIS_URL else None
except Exception:
    REDIS = None


# ----------------------------------------
# Plan Limits (can be overridden in .env)
# ----------------------------------------
DEFAULT_PLAN_LIMITS = {
    "free": int(getattr(settings, "DECISION_FINDER_FREE_DAILY", 20)),
    "pro": int(getattr(settings, "DECISION_FINDER_PRO_DAILY", 200)),
    "enterprise": int(getattr(settings, "DECISION_FINDER_ENT_DAILY", 1_000_000)),
}


# ----------------------------------------
# Internal Helpers
# ----------------------------------------
def _today_ymd() -> str:
    """Return current UTC date as YYYYMMDD string."""
    return datetime.utcnow().strftime("%Y%m%d")


def _seconds_until_utc_midnight() -> int:
    """TTL until next UTC midnight."""
    now = datetime.utcnow()
    tomorrow = now + timedelta(days=1)
    midnight = datetime(tomorrow.year, tomorrow.month, tomorrow.day)
    return int((midnight - now).total_seconds()) + 2  # small buffer


def _quota_key(user_id: int, date_ymd: str = None) -> str:
    if date_ymd is None:
        date_ymd = _today_ymd()
    return f"decision:quota:{user_id}:{date_ymd}"


# ----------------------------------------
# Plan Resolution
# ----------------------------------------
def get_plan_limit_for_user(user_obj) -> int:
    """
    Resolve plan limit based on:
      - user.plan
      - or user.plan_name
      - or user.stripe_plan
    Fallback → free
    """
    if not user_obj:
        return DEFAULT_PLAN_LIMITS["free"]

    plan = (
        getattr(user_obj, "plan", None)
        or getattr(user_obj, "plan_name", None)
        or getattr(user_obj, "stripe_plan", None)
        or "free"
    )

    plan = str(plan).lower()
    return DEFAULT_PLAN_LIMITS.get(plan, DEFAULT_PLAN_LIMITS["free"])


# ----------------------------------------
# Public API
# ----------------------------------------
def get_usage(user_id: int) -> Tuple[int, int]:
    """
    Returns (used, limit_for_free_plan).
    Caller should use get_plan_limit_for_user() for actual plan limit.
    If Redis unavailable → (0, free_limit)
    """
    key = _quota_key(user_id)
    if not REDIS:
        return 0, DEFAULT_PLAN_LIMITS["free"]  # fail-open

    try:
        val = REDIS.get(key)
        used = int(val) if val else 0
        return used, DEFAULT_PLAN_LIMITS["free"]
    except Exception:
        return 0, DEFAULT_PLAN_LIMITS["free"]


def check_and_consume(user_obj, amount: int = 1):
    """
    Atomically consumes `amount` quota units.
    Raises 429 when user exceeds plan limit.
    Returns (used_after, limit).
    """
    if not REDIS:
        return 0, get_plan_limit_for_user(user_obj)  # fail-open

    user_id = getattr(user_obj, "id", None)
    if not user_id:
        raise HTTPException(status_code=401, detail="user_required")

    limit = get_plan_limit_for_user(user_obj)
    key = _quota_key(user_id)

    try:
        used_after = REDIS.incrby(key, amount)

        # Set TTL only when key created
        if used_after == amount:
            ttl = _seconds_until_utc_midnight()
            try:
                REDIS.expire(key, ttl)
            except Exception:
                pass

        if used_after > limit:
            # Rollback over-increment
            try:
                REDIS.decrby(key, amount)
            except Exception:
                pass
            raise HTTPException(
                status_code=429,
                detail="decision_finder_quota_exceeded"
            )

        return used_after, limit

    except HTTPException:
        raise

    except Exception:
        # Fail-open fallback
        return 0, limit
