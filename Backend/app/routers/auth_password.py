# backend/app/routers/auth_password.py
from datetime import datetime, timedelta
import os
import time
import random
import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, status, Depends
from pydantic import BaseModel, EmailStr
from jose import jwt, JWTError
from passlib.context import CryptContext

from backend.app.db import SessionLocal
from backend.app.models.user import User
from backend.app.services.cache import get_cached, set_cached
from backend.app.utils.helpers import send_email  # assumed async
# fallback import for business email check if exists
try:
    from backend.app.utils.email_validator import is_business_email
except Exception:
    def is_business_email(email: str) -> bool:
        # conservative fallback: disallow common free domains
        free = ("gmail.com", "yahoo.com", "hotmail.com", "outlook.com", "icloud.com",
                "aol.com", "protonmail.com", "yandex.com", "mail.ru")
        try:
            domain = email.split("@", 1)[1].lower()
            return domain not in free
        except Exception:
            return False

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])

# Config (use same env names as other auth file)
SECRET_KEY = os.getenv("JWT_SECRET", "replace-this-secret-in-prod")
ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("JWT_ACCESS_EXPIRE_MINUTES", "60"))
REFRESH_TOKEN_EXPIRE_DAYS = int(os.getenv("JWT_REFRESH_EXPIRE_DAYS", "30"))
OTP_TOKEN_EXPIRE_SECONDS = int(os.getenv("OTP_TOKEN_EXPIRE_SECONDS", "600"))  # 10 min
OTP_TTL = int(os.getenv("OTP_TTL", "300"))  # 5 minutes for OTP storage
OTP_RESEND_COOLDOWN = int(os.getenv("OTP_RESEND_COOLDOWN", "60"))  # 60s between sends
OTP_LENGTH = int(os.getenv("OTP_LENGTH", "6"))

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


# ----------------------
# Pydantic schemas
# ----------------------
class SendOtpRequest(BaseModel):
    email: EmailStr


class VerifyOtpRequest(BaseModel):
    email: EmailStr
    otp: str


class SetPasswordRequest(BaseModel):
    otp_token: str
    password: str


class LoginPasswordRequest(BaseModel):
    otp_token: str
    password: str


# ----------------------
# Helpers
# ----------------------
def _otp_cache_key(email: str) -> str:
    return f"otp:{email.lower()}"


def _otp_cooldown_key(email: str) -> str:
    return f"otp:cooldown:{email.lower()}"


def _generate_otp(length: int = OTP_LENGTH) -> str:
    return "".join(random.choices("0123456789", k=length))


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    now = datetime.utcnow()
    if expires_delta:
        expire = now + expires_delta
    else:
        expire = now + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire, "iat": now})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def create_refresh_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    now = datetime.utcnow()
    if expires_delta:
        expire = now + expires_delta
    else:
        expire = now + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode.update({"exp": expire, "iat": now, "type": "refresh"})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def create_otp_token(email: str) -> str:
    """
    Short-lived OTP token (signed). Contains email and marker type.
    Client must present this token to set password or complete login.
    """
    now = datetime.utcnow()
    exp = now + timedelta(seconds=OTP_TOKEN_EXPIRE_SECONDS)
    payload = {"sub": email, "iat": now, "exp": exp, "type": "otp_verification"}
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def decode_otp_token(token: str) -> str:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("type") != "otp_verification":
            raise HTTPException(status_code=401, detail="Invalid OTP token type")
        email = payload.get("sub")
        if not email:
            raise HTTPException(status_code=401, detail="Invalid token payload")
        return email
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired OTP token")


def get_user_by_email(db, email: str) -> Optional[User]:
    return db.query(User).filter(User.email == email).first()


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


# ----------------------
# Routes
# ----------------------

@router.post("/send-otp")
async def send_otp(req: SendOtpRequest):
    email = req.email.lower().strip()

    # 1) Business email enforcement
    if not is_business_email(email):
        logger.info("Blocked non-business signup attempt: %s", email)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="Please use a business (company) email address.")

    # 2) Cooldown check
    try:
        cd = get_cached(_otp_cooldown_key(email))
        if cd:
            raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                                detail=f"OTP recently sent. Try again in {OTP_RESEND_COOLDOWN}s")
    except HTTPException:
        raise
    except Exception:
        logger.debug("Cooldown check failed (ignored)")

    # 3) Generate OTP and cache
    otp = _generate_otp()
    set_cached(_otp_cache_key(email), {"otp": otp, "created_at": int(time.time())}, ttl=OTP_TTL)

    # 4) Set cooldown flag
    set_cached(_otp_cooldown_key(email), {"sent_at": int(time.time())}, ttl=OTP_RESEND_COOLDOWN)

    # 5) Send email (async helper)
    subject = "Your verification code"
    body = f"Your verification code is: {otp}\nThis code will expire in {OTP_TTL // 60} minutes."
    try:
        await send_email(to=email, subject=subject, body=body)
    except Exception:
        logger.exception("Failed to send OTP email to %s", email)
        raise HTTPException(status_code=500, detail="Failed to send OTP email")

    return {"message": "OTP sent to business email."}


@router.post("/verify-otp")
async def verify_otp(req: VerifyOtpRequest):
    email = req.email.lower().strip()
    otp_input = str(req.otp).strip()

    # read OTP cache
    try:
        cached = get_cached(_otp_cache_key(email))
    except Exception:
        cached = None

    if not cached:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="OTP expired or not found")

    otp_saved = str(cached.get("otp", ""))
    if otp_saved != otp_input:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid OTP")

    # OTP correct -> create short-lived token and remove OTP (best-effort)
    try:
        set_cached(_otp_cache_key(email), {}, ttl=1)  # clear quickly
    except Exception:
        pass

    # create otp_token for next stage (set-password or login-password)
    otp_token = create_otp_token(email)

    # check if user exists
    db = SessionLocal()
    try:
        user = get_user_by_email(db, email)
        exists = bool(user)
    finally:
        try:
            db.close()
        except Exception:
            pass

    return {"ok": True, "user_exists": exists, "otp_token": otp_token}


@router.post("/set-password")
async def set_password(req: SetPasswordRequest):
    # For new users: require otp_token and password, create user, mark verified, return JWTs
    email = decode_otp_token(req.otp_token).lower().strip()
    password = req.password

    if not password or len(password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")

    db = SessionLocal()
    try:
        user = get_user_by_email(db, email)
        if user:
            # if user exists, don't override here; instruct to login instead
            raise HTTPException(status_code=400, detail="User already exists; use login flow")

        # Create user
        user = User(email=email, hashed_password=hash_password(password), is_active=True, email_verified=True)
        db.add(user)
        db.commit()
        db.refresh(user)

        # optional: create a team (best-effort)
        try:
            from backend.app.models.team import Team
            team_name = email.split("@", 1)[1].split(".")[0] + " Team"
            team = Team(name=team_name, owner_id=user.id)
            db.add(team)
            db.commit()
        except Exception:
            try:
                db.rollback()
            except Exception:
                pass
            logger.debug("Team creation failed (ignored) for %s", email)

        # issue tokens
        access_token = create_access_token({"sub": str(user.id), "email": user.email})
        refresh_token = create_refresh_token({"sub": str(user.id), "email": user.email})

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("set_password error: %s", e)
        raise HTTPException(status_code=500, detail="Failed to create user")
    finally:
        try:
            db.close()
        except Exception:
            pass

    return {"message": "User created", "access_token": access_token, "refresh_token": refresh_token, "user_id": user.id}


@router.post("/login-password")
async def login_password(req: LoginPasswordRequest):
    # For existing users: require otp_token (to prove email) and password (to authenticate)
    email = decode_otp_token(req.otp_token).lower().strip()
    password = req.password

    db = SessionLocal()
    try:
        user = get_user_by_email(db, email)
        if not user:
            raise HTTPException(status_code=404, detail="User not found; sign up first")

        if not user.hashed_password:
            raise HTTPException(status_code=400, detail="Password not set; complete sign up")

        if not verify_password(password, user.hashed_password):
            raise HTTPException(status_code=401, detail="Incorrect password")

        if not getattr(user, "is_active", True):
            raise HTTPException(status_code=403, detail="User not active")

        # success: create tokens
        access_token = create_access_token({"sub": str(user.id), "email": user.email})
        refresh_token = create_refresh_token({"sub": str(user.id), "email": user.email})

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("login-password error: %s", e)
        raise HTTPException(status_code=500, detail="Login failed")
    finally:
        try:
            db.close()
        except Exception:
            pass

    return {"access_token": access_token, "refresh_token": refresh_token, "user_id": user.id}
