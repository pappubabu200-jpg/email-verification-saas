from pydantic import BaseModel, EmailStr
from datetime import datetime
from .base import ORMBase


class UserBase(BaseModel):
    email: EmailStr
    is_active: bool | None = True
    is_admin: bool | None = False
    email_verified: bool | None = False

    first_name: str | None = None
    last_name: str | None = None
    country: str | None = None
    timezone: str | None = None

    plan: str | None = None
    credits: float | None = 0
    stripe_customer_id: str | None = None


class UserCreate(BaseModel):
    email: EmailStr
    password: str


class UserUpdate(BaseModel):
    first_name: str | None = None
    last_name: str | None = None
    country: str | None = None
    timezone: str | None = None


class UserResponse(ORMBase, UserBase):
    pass
