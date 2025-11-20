from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.app.db import SessionLocal
from backend.app.utils.security import get_current_user
from backend.app.services.api_key_service import create_api_key, deactivate_api_key
from backend.app.models.api_key import ApiKey

router = APIRouter(prefix="/v1/api-keys", tags=["API Keys"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.post("/create")
def create_key(name: str = None, current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    key = create_api_key(db, current_user.id, name)
    return {"id": key.id, "key": key.key, "name": key.name, "daily_limit": key.daily_limit}


@router.get("/list")
def list_keys(current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    keys = db.query(ApiKey).filter(ApiKey.user_id == current_user.id).all()
    return keys


@router.post("/revoke/{key_id}")
def revoke_key(key_id: int, current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    deactivate_api_key(db, key_id, current_user.id)
    return {"status": "revoked"}
