import secrets
from datetime import datetime
from sqlalchemy.orm import Session
from fastapi import HTTPException

from backend.app.models.api_key import ApiKey


def generate_api_key() -> str:
    """Generate a 64-byte secure API key."""
    return secrets.token_hex(32)


def create_api_key(db: Session, user_id: int, name: str = None) -> ApiKey:
    key = generate_api_key()

    api_key = ApiKey(
        user_id=user_id,
        key=key,
        name=name,
        active=True,
        used_today=0,
        daily_limit=5000,
    )
    db.add(api_key)
    db.commit()
    db.refresh(api_key)
    return api_key


def get_api_key(db: Session, key: str) -> ApiKey:
    api_key = db.query(ApiKey).filter(ApiKey.key == key, ApiKey.active == True).first()
    if not api_key:
        raise HTTPException(status_code=401, detail="invalid_api_key")
    return api_key


def deactivate_api_key(db: Session, api_key_id: int, user_id: int) -> bool:
    api_key = db.query(ApiKey).filter(ApiKey.id == api_key_id, ApiKey.user_id == user_id).first()
    if not api_key:
        raise HTTPException(status_code=404, detail="api_key_not_found")

    api_key.active = False
    db.commit()
    return True


def increment_usage(db: Session, key_id: int):
    api_key = db.query(ApiKey).filter(ApiKey.id == key_id).first()
    if not api_key:
        return
    api_key.used_today += 1
    if api_key.used_today > api_key.daily_limit:
        raise HTTPException(status_code=429, detail="api_key_daily_limit_reached")
    db.commit()


def create_api_key(db: Session, user_id: int, name: str = None, daily_limit: int = 5000, rate_limit_per_sec: int = 0) -> ApiKey:
    key = generate_api_key()

    api_key = ApiKey(
        user_id=user_id,
        key=key,
        name=name,
        active=True,
        used_today=0,
        daily_limit=daily_limit,
        rate_limit_per_sec=rate_limit_per_sec,
    )
    db.add(api_key)
    db.commit()
    db.refresh(api_key)
    return api_key
