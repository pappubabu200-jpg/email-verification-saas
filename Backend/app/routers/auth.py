# backend/app/routers/auth.py
from datetime import datetime, timedelta
import os
from typing import AsyncGenerator

from fastapi import APIRouter, Depends, HTTPException, status, Response
from fastapi.security import OAuth2PasswordRequestForm
from jose import jwt, JWTError  # pip install python-jose[cryptography]
from passlib.context import CryptContext  # pip install passlib[bcrypt]
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.schemas.user import UserCreate, UserResponse
from backend.app.repositories.user_repository import UserRepository
from backend.app.models import User  # type: ignore
from backend.app.schemas.base import ORMBase

# -------------------------
# CONFIG
# -------------------------
SECRET_KEY = os.getenv("JWT_SECRET", "replace-this-secret-in-prod")
ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("JWT_ACCESS_EXPIRE_MINUTES", "60"))
REFRESH_TOKEN_EXPIRE_DAYS = int(os.getenv("JWT_REFRESH_EXPIRE_DAYS", "30"))

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

router = APIRouter(prefix="/auth", tags=["auth"])


# -------------------------
# DB dependency (swap with your get_db)
# -------------------------
# NOTE: replace this with your actual get_db dependency that yields AsyncSession.
# For example, from backend.app.db import get_async_db
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Placeholder get_db. Replace with your actual implementation.
    Example:
        from backend.app.db import async_session
        async with async_session() as session:
            yield session
    """
    from backend.app.db import async_session  # update to your actual name
    async with async_session() as session:
        yield session


# -------------------------
# Utilities
# -------------------------
def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)


def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
    to_encode = data.copy()
    now = datetime.utcnow()
    if expires_delta:
        expire = now + expires_delta
    else:
        expire = now + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire, "iat": now})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def create_refresh_token(data: dict, expires_delta: timedelta | None = None) -> str:
    to_encode = data.copy()
    now = datetime.utcnow()
    if expires_delta:
        expire = now + expires_delta
    else:
        expire = now + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode.update({"exp": expire, "iat": now, "type": "refresh"})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


async def get_current_user(token: str = Depends(lambda: None), db: AsyncSession | None = None):
    """
    Example helper for dependency injection when needed by other routers.
    In real usage you will use OAuth2PasswordBearer or cookie extraction.
    """
    raise NotImplementedError("Use OAuth2PasswordBearer or cookie extraction in your routes.")


# -------------------------
# Small helpers (email verification + send)
# -------------------------
async def send_verification_email(email: str, token: str):
    """
    TODO: replace with your actual email sending logic (async).
    This function should send a verification link to: /auth/verify-email?token=...
    """
    # Example: await email_service.send_verification(email, token)
    pass


def decode_token(token: str) -> dict:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token") from exc


# -------------------------
# ROUTES
# -------------------------

@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(user_in: UserCreate, db: AsyncSession = Depends(get_db)):
    """
    Create a new user (register).
    - Hashes password
    - Creates user record
    - Optionally sends verification email
    """
    user_repo = UserRepository(db)
    existing = await user_repo.get_by_email(user_in.email)
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")

    hashed = get_password_hash(user_in.password)
    user_obj = await user_repo.create({"email": user_in.email, "hashed_password": hashed})

    # Create an email verification token (signed JWT)
    verify_token = create_access_token({"sub": str(user_obj.id), "email": user_obj.email}, expires_delta=timedelta(hours=24))
    # enqueue or send verification email (async)
    await send_verification_email(user_obj.email, verify_token)

    return UserResponse.from_orm(user_obj)


@router.post("/login")
async def login(response: Response, form_data: OAuth2PasswordRequestForm = Depends(), db: AsyncSession = Depends(get_db)):
    """
    Login using email + password (OAuth2PasswordRequestForm compatible).
    Returns access_token and refresh_token (in body).
    You may also set cookies (HttpOnly) if desired.
    """
    user_repo = UserRepository(db)
    user = await user_repo.get_by_email(form_data.username)
    if not user:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Incorrect email or password")

    if not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Incorrect email or password")

    # Check active
    if not getattr(user, "is_active", True):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User not active")

    access_token = create_access_token({"sub": str(user.id), "email": user.email})
    refresh_token = create_refresh_token({"sub": str(user.id), "email": user.email})

    # Optionally set cookies (uncomment if you want cookie-based auth)
    # response.set_cookie("access_token", access_token, httponly=True, secure=True, samesite="lax")
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "refresh_token": refresh_token,
        "user": UserResponse.from_orm(user),
    }


@router.post("/refresh")
async def refresh_token(payload: dict, db: AsyncSession = Depends(get_db)):
    """
    Accepts JSON body with {"refresh_token": "..."} and returns new access token.
    """
    token = payload.get("refresh_token") if isinstance(payload, dict) else None
    if not token:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing refresh_token")

    try:
        data = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")

    if data.get("type") != "refresh":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token is not refresh type")

    user_id = int(data.get("sub"))
    user_repo = UserRepository(db)
    user = await user_repo.get(user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    access_token = create_access_token({"sub": str(user.id), "email": user.email})
    refresh_token = create_refresh_token({"sub": str(user.id), "email": user.email})
    return {"access_token": access_token, "token_type": "bearer", "refresh_token": refresh_token}


@router.post("/logout")
async def logout(response: Response):
    """
    Logout endpoint. If you use cookies, clear them here.
    With token-based stateless JWT, instruct client to drop tokens.
    """
    # If you set cookies in login, clear them here:
    # response.delete_cookie("access_token")
    return {"ok": True}


@router.get("/verify-email")
async def verify_email(token: str, db: AsyncSession = Depends(get_db)):
    """
    Simple email verification endpoint.
    - decode token (contains user id)
    - mark email_verified=True on user
    """
    try:
        payload = decode_token(token)
        uid = int(payload.get("sub"))
    except Exception:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired token")

    user_repo = UserRepository(db)
    user = await user_repo.get(uid)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    await user_repo.update(user, {"email_verified": True})
    return {"ok": True}
