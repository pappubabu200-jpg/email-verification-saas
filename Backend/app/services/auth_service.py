# backend/app/services/auth_service.py

import os
from datetime import datetime
from typing import Optional

from fastapi import Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordBearer
from jose import jwt, JWTError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db import async_session
from backend.app.repositories.user_repository import UserRepository

# ---------------------------------------------------
# CONFIG
# ---------------------------------------------------

SECRET_KEY = os.getenv("JWT_SECRET", "replace-this-secret")
ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")

# ---------------------------------------------------
# DB Dependency
# ---------------------------------------------------

async def get_db():
    async with async_session() as session:
        yield session


# ---------------------------------------------------
# TOKEN DECODING
# ---------------------------------------------------

def decode_token(token: str) -> dict:
    """Decodes JWT token and returns payload dict."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )


# ---------------------------------------------------
# EXTRACT TOKEN (HEADER or COOKIE)
# ---------------------------------------------------

def extract_token(request: Request, token_from_auth: Optional[str]) -> str:
    """
    Token can come from:
    - Authorization: Bearer ...
    - Cookies: access_token
    This function unifies both.
    """
    # 1. Cookie first (if you use cookie auth)
    cookie_token = request.cookies.get("access_token")
    if cookie_token:
        return cookie_token

    # 2. Bearer token (OAuth2PasswordBearer)
    if token_from_auth:
        return token_from_auth

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated",
    )


# ---------------------------------------------------
# CURRENT USER DEPENDENCY
# ---------------------------------------------------

async def get_current_user(
    request: Request,
    token_from_auth: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
):
    """
    Extract JWT → decode → load user → verify active.
    This is used in all protected routers.
    """

    # Get access token (header or cookie)
    token = extract_token(request, token_from_auth)

    # Decode JWT
    payload = decode_token(token)
    user_id = payload.get("sub")

    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
        )

    # Load user
    repo = UserRepository(db)
    user = await repo.get(int(user_id))

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    # Check account status
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is inactive",
        )

    return user


# ---------------------------------------------------
# ADMIN-ONLY DEPENDENCY
# ---------------------------------------------------

async def get_current_admin(
    current_user = Depends(get_current_user)
):
    """Verify that user is admin."""
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access only",
        )
    return current_user
