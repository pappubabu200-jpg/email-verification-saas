# backend/app/services/api_key_service.py

import logging
from sqlalchemy.orm import Session
from sqlalchemy import select, update
from fastapi import HTTPException

from backend.app.db import SessionLocal
from backend.app.models.api_key import ApiKey

# Redis support
try:
    import redis
    from backend.app.config import settings
    REDIS = redis.from_url(settings.REDIS_URL)
except Exception:
    REDIS = None

logger = logging.getLogger(__name__)


# ---------------------------------------------------------
# REDIS FAST COUNTER HELPERS
# ---------------------------------------------------------

def _redis_usage_key(api_key_id: int) -> str:
    return f"api_key:{api_key_id}:used_today"


def redis_increment_usage(api_key_row: ApiKey, amount: int = 1):
    """
    If Redis is available, increment fast counter.
    Returns new value or None (if Redis unavailable).
    """
    if not REDIS:
        return None

    try:
        key = _redis_usage_key(api_key_row.id)
        new_val = REDIS.incrby(key, amount)

        # set TTL = 24 hours
        if new_val == amount:
            REDIS.expire(key, 86400)

        return new_val

    except Exception as e:
        logger.debug(f"Redis increment error: {e}")
        return None


# ---------------------------------------------------------
# API KEY LOOKUPS
# ---------------------------------------------------------

def get_api_key(db: Session, raw_key: str) -> ApiKey:
    """Return ApiKey row for given API key string OR raise 401."""
    if not raw_key:
        raise HTTPException(status_code=401, detail="api_key_required")

    ak = db.query(ApiKey).filter(ApiKey.key == raw_key, ApiKey.active == True).first()
    if not ak:
        raise HTTPException(status_code=401, detail="invalid_api_key")

    return ak


def get_api_key_optional(db: Session, raw_key: str) -> ApiKey:
    """Return ApiKey row or None (no exception)."""
    if not raw_key:
        return None
    return db.query(ApiKey).filter(ApiKey.key == raw_key).first()


# ---------------------------------------------------------
# DAILY USAGE COUNTER (REDIS FIRST → SQL FALLBACK)
# ---------------------------------------------------------

def increment_usage(db: Session, api_key_row: ApiKey, amount: int = 1) -> dict:
    """
    Increment used_today by `amount` and enforce daily_limit.

    Order:
    A) Redis fast counter (atomic, high performance)
    B) SQL fallback if Redis unavailable
    """

    if not api_key_row:
        raise HTTPException(status_code=401, detail="api_key_required")

    if not api_key_row.active:
        raise HTTPException(status_code=403, detail="api_key_disabled")

    # ---------------------------------------------------------
    # (A) REDIS FAST PATH
    # ---------------------------------------------------------
    redis_count = redis_increment_usage(api_key_row, amount)
    if redis_count is not None:

        # enforce limit
        if api_key_row.daily_limit and redis_count > api_key_row.daily_limit:
            try:
                REDIS.decrby(_redis_usage_key(api_key_row.id), amount)
            except Exception:
                pass
            raise HTTPException(status_code=429, detail="daily_api_key_limit_exceeded")

        return {
            "used": redis_count,
            "daily_limit": api_key_row.daily_limit,
            "ok": True
        }

    # ---------------------------------------------------------
    # (B) SQL FALLBACK
    # ---------------------------------------------------------
    try:
        stmt = (
            update(ApiKey)
            .where(ApiKey.id == api_key_row.id)
            .values(used_today=ApiKey.used_today + amount)
            .returning(ApiKey.used_today)
        )
        new_used = db.execute(stmt).scalar()
        db.commit()

        new_used = int(new_used)

        if api_key_row.daily_limit and new_used > api_key_row.daily_limit:
            raise HTTPException(status_code=429, detail="daily_api_key_limit_exceeded")

        return {
            "used": new_used,
            "daily_limit": api_key_row.daily_limit,
            "ok": True
        }

    except Exception as e:
        logger.exception("SQL usage increment failed: %s", e)
        db.rollback()
        raise HTTPException(status_code=500, detail="increment_failed")


# ---------------------------------------------------------
# ADMIN RESET (optional)
# ---------------------------------------------------------

def reset_usage(db: Session, api_key_id: int):
    """Admin-only reset usage counters."""
    try:
        stmt = (
            update(ApiKey)
            .where(ApiKey.id == api_key_id)
            .values(used_today=0)
        )
        db.execute(stmt)
        db.commit()

        # reset Redis too
        if REDIS:
            REDIS.delete(_redis_usage_key(api_key_id))

        return {"status": "ok", "reset": api_key_id}

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail="reset_failed")
