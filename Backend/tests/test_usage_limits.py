import pytest
from backend.app.services.api_key_service import increment_usage, redis_increment_usage, reset_all_api_keys_usage
from backend.app.db import SessionLocal
from backend.app.models.api_key import ApiKey

@pytest.fixture
def db():
    db = SessionLocal()
    yield db
    db.close()

def test_db_increment_usage(db):
    # create api key
    ak = ApiKey(
        user_id=1,
        key="test_db",
        active=True,
        daily_limit=10,
        used_today=0,
        rate_limit_per_sec=5
    )
    db.add(ak)
    db.commit()
    db.refresh(ak)

    out = increment_usage(db, ak, amount=1)
    assert out["used"] == 1

def test_db_over_usage(db):
    ak = ApiKey(
        user_id=1,
        key="test_db_limit",
        active=True,
        daily_limit=1,
        used_today=1,
        rate_limit_per_sec=5
    )
    db.add(ak)
    db.commit()
    db.refresh(ak)

    with pytest.raises(Exception):
        increment_usage(db, ak, amount=1)

def test_reset_all(db):
    ak = ApiKey(
        user_id=1,
        key="test_reset",
        active=True,
        daily_limit=10,
        used_today=7,
        rate_limit_per_sec=5
    )
    db.add(ak)
    db.commit()

    reset_all_api_keys_usage()
    db.refresh(ak)
    assert ak.used_today == 0
