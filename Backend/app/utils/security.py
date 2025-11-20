from typing import Optional, Dict, Any
from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import jwt
from datetime import datetime, timedelta

from backend.app.config import settings
from backend.app.db import SessionLocal
from backend.app.models.user import User

security = HTTPBearer()

def create_access_token(data: Dict[str, Any], expires_delta: Optional[int] = None) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(seconds=(expires_delta or settings.ACCESS_TOKEN_EXPIRE_SECONDS))
    to_encode.update({"exp": expire})
    token = jwt.encode(to_encode, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
    return token

def decode_token(token: str) -> Dict[str, Any]:
    try:
        payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="token_expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="invalid_token")

def get_current_user(creds: HTTPAuthorizationCredentials = Depends(security)) -> User:
    payload = decode_token(creds.credentials)
    sub = payload.get("sub")
    if not sub:
        raise HTTPException(status_code=401, detail="invalid_token_payload")
    try:
        user_id = int(sub)
    except Exception:
        raise HTTPException(status_code=401, detail="invalid_user_id")

    db = SessionLocal()
    try:
        user = db.get(User, user_id)
        if not user:
            raise HTTPException(status_code=401, detail="user_not_found")
        return user
    finally:
        db.close()

def get_current_admin(creds: HTTPAuthorizationCredentials = Depends(security)) -> User:
    user = get_current_user(creds)
    if not getattr(user, "is_admin", False):
        raise HTTPException(status_code=403, detail="admin_required")
    return user
