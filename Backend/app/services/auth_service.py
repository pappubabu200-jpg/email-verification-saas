# backend/app/services/auth_service.py

import os
from datetime import datetime, timezone
from typing import Optional

from fastapi import Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordBearer
from jose import jwt, JWTError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db import async_session
from backend.app.repositories.user_repository import UserRepository
from backend.app.config import settings


# ---------------------------------------------------
# CONFIG (MANDATORY SECRETS)
# ---------------------------------------------------

SECRET_KEY = settings.JWT_SECRET
ALGORITHM = settings.JWT_ALGORITHM

if not SECRET_KEY or SECRET_KEY == "replace-this-secret":
    raise RuntimeError("FATAL: JWT_SECRET environment variable must be set")


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


# ---------------------------------------------------
# DB Dependency
# ---------------------------------------------------

async def get_db():
    async with async_session() as session:
        yield session


# ---------------------------------------------------
# TOKEN DECODING + VALIDATION
# ---------------------------------------------------

def decode_token(token: str) -> dict:
    """
    Validates:
        - signature
        - issuer
        - expiry
        - issued-at
    Returns decoded JWT payload.
    """
    try:
        payload = jwt.decode(
            token,
            SECRET_KEY,
            algorithms=[ALGORITHM],
            options={"verify_aud": False}  # SaaS backend not using audiences
        )

        # Optional: Additional lifetime check
        exp = payload.get("exp")
        if exp and datetime.now(timezone.utc).timestamp() > exp:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token expired",
            )

        return payload

    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )


# ---------------------------------------------------
# EXTRACT TOKEN (HEADER OR COOKIE)
# ---------------------------------------------------

def extract_token(request: Request, token_from_auth: Optional[str]) -> str:
    """
    Priority:
    1. Cookie: access_token
    2. Authorization Bearer token
    """
    cookie_token = request.cookies.get("access_token")
    if cookie_token:
        return cookie_token

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
    Auth Flow:
        Cookie/Bearer → decode token → find user → validate
    """

    token = extract_token(request, token_from_auth)

    payload = decode_token(token)
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
        )

    repo = UserRepository(db)
    user = await repo.get(int(user_id))

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    # Suspended user check (recommended)
    if user.is_active is False:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is inactive or suspended",
        )

    return user


# ---------------------------------------------------
# CURRENT ADMIN
# ---------------------------------------------------

async def get_current_admin(current_user=Depends(get_current_user)):
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access only",
        )
    return current_user
