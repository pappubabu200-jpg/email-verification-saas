# backend/app/services/api_key_service.py

import logging
from fastapi import HTTPException

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db import async_session
from backend.app.models.api_key import ApiKey

# Async Redis
try:
    import redis.asyncio as redis
    from backend.app.config import settings
    REDIS = redis.from_url(settings.REDIS_URL)
except Exception:
    REDIS = None

logger = logging.getLogger(__name__)


# ---------------------------------------------------------
# REDIS HELPERS
# ---------------------------------------------------------
def _redis_usage_key(api_key_id: int) -> str:
    return f"api_key:{api_key_id}:used_today"


async def redis_increment_usage(api_key_row: ApiKey, amount: int = 1):
    """Async + atomic increment."""
    if not REDIS:
        return None

    try:
        key = _redis_usage_key(api_key_row.id)

        new_val = await REDIS.incrby(key, amount)

        # Set 24-hour expiration only on first increment
        if new_val == amount:
            await REDIS.expire(key, 86400)

        return new_val

    except Exception as e:
        logger.debug(f"Redis error: {e}")
        return None


# ---------------------------------------------------------
# GET API KEY
# ---------------------------------------------------------
async def get_api_key(db: AsyncSession, raw_key: str) -> ApiKey:
    if not raw_key:
        raise HTTPException(status_code=401, detail="api_key_required")

    stmt = select(ApiKey).where(
        ApiKey.key_hash == ApiKey.hash_key(raw_key),
        ApiKey.active == True
    )

    result = await db.execute(stmt)
    api_key = result.scalar_one_or_none()

    if not api_key:
        raise HTTPException(status_code=401, detail="invalid_api_key")

    return api_key


async def get_api_key_optional(db: AsyncSession, raw_key: str):
    if not raw_key:
        return None

    stmt = select(ApiKey).where(ApiKey.key_hash == ApiKey.hash_key(raw_key))
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


# ---------------------------------------------------------
# INCREMENT USAGE (REDIS → SQL FALLBACK)
# ---------------------------------------------------------
async def increment_usage(db: AsyncSession, api_key_row: ApiKey, amount: int = 1):
    if not api_key_row:
        raise HTTPException(status_code=401, detail="api_key_required")

    if not api_key_row.active:
        raise HTTPException(status_code=403, detail="api_key_disabled")

    # (A) Redis fast counter
    redis_count = await redis_increment_usage(api_key_row, amount)

    if redis_count is not None:
        if api_key_row.daily_limit and redis_count > api_key_row.daily_limit:
            # rollback redis increment
            await REDIS.decrby(_redis_usage_key(api_key_row.id), amount)
            raise HTTPException(status_code=429, detail="daily_api_key_limit_exceeded")

        return {
            "used": redis_count,
            "daily_limit": api_key_row.daily_limit,
            "ok": True
        }

    # (B) SQL fallback
    try:
        stmt = (
            update(ApiKey)
            .where(ApiKey.id == api_key_row.id)
            .values(used_today=ApiKey.used_today + amount)
            .returning(ApiKey.used_today)
        )

        res = await db.execute(stmt)
        await db.commit()

        new_used = int(res.scalar() or 0)

        if api_key_row.daily_limit and new_used > api_key_row.daily_limit:
            raise HTTPException(status_code=429, detail="daily_api_key_limit_exceeded")

        return {
            "used": new_used,
            "daily_limit": api_key_row.daily_limit,
            "ok": True
        }

    except Exception as e:
        await db.rollback()
        logger.error("Usage increment failed: %s", e)
        raise HTTPException(status_code=500, detail="increment_failed")


# ---------------------------------------------------------
# ADMIN RESET
# ---------------------------------------------------------
async def reset_usage(db: AsyncSession, api_key_id: int):
    stmt = (
        update(ApiKey)
        .where(ApiKey.id == api_key_id)
        .values(used_today=0)
    )

    try:
        await db.execute(stmt)
        await db.commit()

        if REDIS:
            await REDIS.delete(_redis_usage_key(api_key_id))

        return {"status": "ok", "reset": api_key_id}

    except Exception:
        await db.rollback()
        raise HTTPException(status_code=500, detail="reset_failed")
