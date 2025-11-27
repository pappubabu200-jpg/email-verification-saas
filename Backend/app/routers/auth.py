from datetime import datetime, timedelta
import os
import time
import random
from typing import AsyncGenerator, Optional

from fastapi import APIRouter, Depends, HTTPException, status, Response
from fastapi.security import OAuth2PasswordRequestForm
from jose import jwt, JWTError
from passlib.context import CryptContext
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db import async_session
from backend.app.repositories.user_repository import UserRepository
from backend.app.models.user import User
from backend.app.utils.helpers import send_email
from backend.app.services.cache import get_cached, set_cached

# -----------------------------------------------------
# CONFIG
# -----------------------------------------------------
SECRET_KEY = os.getenv("JWT_SECRET", "replace-this-secret-in-prod")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60
REFRESH_TOKEN_EXPIRE_DAYS = 30

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

router = APIRouter(prefix="/auth", tags=["Auth"])


# -----------------------------------------------------
# DB Session
# -----------------------------------------------------
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with async_session() as session:
        yield session


# -----------------------------------------------------
# JWT UTILS
# -----------------------------------------------------
def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    now = datetime.utcnow()
    expire = now + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire, "iat": now})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def create_refresh_token(data: dict):
    to_encode = data.copy()
    now = datetime.utcnow()
    expire = now + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode.update({"exp": expire, "iat": now, "type": "refresh"})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


# -----------------------------------------------------
# BUSINESS EMAIL CHECK
# -----------------------------------------------------
def is_business_email(email: str) -> bool:
    free_domains = {
        "gmail.com", "yahoo.com", "hotmail.com", "outlook.com",
        "aol.com", "icloud.com", "protonmail.com", "yandex.com"
    }
    domain = email.split("@")[-1].lower()
    return domain not in free_domains


# -----------------------------------------------------
# OTP HELPERS
# -----------------------------------------------------
OTP_TTL = 300                # 5 mins
OTP_RESEND_COOLDOWN = 60     # 1 min
OTP_LENGTH = 6

def otp_key(email: str): return f"otp:{email}"
def otp_cd_key(email: str): return f"otp_cd:{email}"

def generate_otp(): return "".join(random.choices("0123456789", k=OTP_LENGTH))


# -----------------------------------------------------
# SEND OTP
# -----------------------------------------------------
@router.post("/send-otp")
async def send_otp(data: dict):
    email = data.get("email", "").lower().strip()

    if not is_business_email(email):
        raise HTTPException(400, "Use a business/company email.")

    # Cooldown check
    if get_cached(otp_cd_key(email)):
        raise HTTPException(429, f"OTP recently sent. Try again in {OTP_RESEND_COOLDOWN}s")

    # Generate + Save OTP
    otp = generate_otp()
    set_cached(otp_key(email), {"otp": otp, "ts": time.time()}, ttl=OTP_TTL)
    set_cached(otp_cd_key(email), {"cd": True}, ttl=OTP_RESEND_COOLDOWN)

    # Send email
    subject = "Your Verification Code"
    body = f"Your verification code is {otp}. It is valid for 5 minutes."

    try:
        await send_email(to=email, subject=subject, body=body)
    except Exception:
        raise HTTPException(500, "Failed to send OTP")

    return {"message": "OTP sent successfully", "email": email}


# -----------------------------------------------------
# VERIFY OTP
# -----------------------------------------------------
@router.post("/verify-otp")
async def verify_otp(data: dict, db: AsyncSession = Depends(get_db)):
    email = data.get("email", "").lower()
    otp = data.get("otp", "")

    saved = get_cached(otp_key(email))
    if not saved or saved.get("otp") != otp:
        raise HTTPException(400, "Invalid or expired OTP")

    # Create or get user
    repo = UserRepository(db)
    user = await repo.get_by_email(email)
    created = False

    if not user:
        user = await repo.create({"email": email})
        created = True

    return {
        "message": "OTP verified",
        "user_id": user.id,
        "email": user.email,
        "is_new": created
    }


# -----------------------------------------------------
# SET PASSWORD
# -----------------------------------------------------
@router.post("/set-password")
async def set_password(data: dict, db: AsyncSession = Depends(get_db)):
    user_id = data.get("user_id")
    password = data.get("password")

    if not user_id or not password:
        raise HTTPException(400, "Missing user_id or password")

    repo = UserRepository(db)
    user = await repo.get(user_id)
    if not user:
        raise HTTPException(404, "User not found")

    hashed = hash_password(password)
    await repo.update(user, {"hashed_password": hashed})

    return {"ok": True, "message": "Password set successfully"}


# -----------------------------------------------------
# LOGIN
# -----------------------------------------------------
@router.post("/login")
async def login(form: OAuth2PasswordRequestForm = Depends(),
                db: AsyncSession = Depends(get_db)):

    repo = UserRepository(db)
    user = await repo.get_by_email(form.username)
    if not user or not user.hashed_password:
        raise HTTPException(400, "Incorrect email or password")

    if not verify_password(form.password, user.hashed_password):
        raise HTTPException(400, "Incorrect email or password")

    return {
        "access_token": create_access_token({"sub": str(user.id)}),
        "refresh_token": create_refresh_token({"sub": str(user.id)}),
        "token_type": "bearer"
    }
