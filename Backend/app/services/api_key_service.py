# backend/app/services/api_key_service.py
import logging
from sqlalchemy.orm import Session
from sqlalchemy import select, update
from fastapi import HTTPException

from backend.app.db import SessionLocal
from backend.app.models.api_key import ApiKey

logger = logging.getLogger(__name__)

def get_api_key(db: Session, raw_key: str) -> ApiKey:
    """
    Return ApiKey row for given API key string or raise HTTPException(401).
    """
    if not raw_key:
        raise HTTPException(status_code=401, detail="api_key_required")
    ak = db.query(ApiKey).filter(ApiKey.key == raw_key, ApiKey.active == True).first()
    if not ak:
        raise HTTPException(status_code=401, detail="invalid_api_key")
    return ak

def get_api_key_optional(db: Session, raw_key: str):
    """
    Return ApiKey row or None (no exception). Use when you want permissive behavior.
    """
    if not raw_key:
        return None
    return db.query(ApiKey).filter(ApiKey.key == raw_key).first()

def increment_usage(db: Session, api_key_row: ApiKey, amount: int = 1) -> dict:
    """
    Increment used_today by `amount` and check daily_limit.
    Returns dict: {"used": int, "daily_limit": int, "ok": bool}
    Raises HTTPException(429) if over limit (soft-block).
    Uses a DB row update: UPDATE api_keys SET used_today = used_today + amount WHERE id = ...
    """
    if not api_key_row:
        raise HTTPException(status_code=401, detail="api_key_required")

    if not api_key_row.active:
        raise HTTPException(status_code=403, detail="api_key_disabled")

    # If daily_limit==0 treat as unlimited
    try:
        new_used = None
        # atomic update via SQL expression to avoid race (ORM may not be perfectly atomic across processes,
        # but this pattern helps; for heavy load you should use Redis counters or DB-level locking)
        stmt = (
            update(ApiKey)
            .where(ApiKey.id == api_key_row.id)
            .values(used_today = ApiKey.used_today + amount)
            .returning(ApiKey.used_today, ApiKey.daily_limit)
        )
        res = db.execute(stmt)
        row = res.fetchone()
        db.commit()
        if row:
            new_used, daily_limit = int(row[0]), int(row[1] or 0)
        else:
            # fallback to reload
            db.refresh(api_key_row)
            new_used = int(api_key_row.used_today)
            daily_limit = int(api_key_row.daily_limit or 0)
    except Exception as e:
        logger.exception("increment_usage DB error: %s", e)
        # permissive fallback (allow) to avoid blocking in DB outage
        return {"used": api_key_row.used_today or 0, "daily_limit": api_key_row.daily_limit or 0, "ok": True}

    # daily_limit == 0 => unlimited
    if daily_limit and new_used > daily_limit:
        # Rollback action: decrement back the amount to avoid overshoot
        try:
            stmt2 = update(ApiKey).where(ApiKey.id == api_key_row.id).values(used_today = ApiKey.used_today - amount)
            db.execute(stmt2)
            db.commit()
        except Exception:
            logger.debug("rollback decrement failed after exceeding limit")

        raise HTTPException(status_code=429, detail="daily_api_key_limit_exceeded")

    return {"used": new_used, "daily_limit": daily_limit, "ok": True}

def set_api_key_active(db: Session, api_key_id: int, active: bool = True) -> ApiKey:
    """
    Enable/disable API key.
    """
    ak = db.query(ApiKey).get(api_key_id)
    if not ak:
        raise HTTPException(status_code=404, detail="api_key_not_found")
    ak.active = bool(active)
    db.add(ak)
    db.commit()
    db.refresh(ak)
    return ak

def reset_api_key_usage(db: Session, api_key_id: int):
    """
    Reset used_today to zero for a single api key.
    """
    ak = db.query(ApiKey).get(api_key_id)
    if not ak:
        raise HTTPException(status_code=404, detail="api_key_not_found")
    ak.used_today = 0
    db.add(ak)
    db.commit()
    db.refresh(ak)
    return ak

def reset_all_api_keys_usage():
    """
    Reset used_today=0 for all keys. Intended to be called daily by Celery beat or cron.
    """
    db = SessionLocal()
    try:
        db.query(ApiKey).update({ApiKey.used_today: 0})
        db.commit()
    except Exception as e:
        logger.exception("reset_all_api_keys_usage failed: %s", e)
    finally:
        db.close()
