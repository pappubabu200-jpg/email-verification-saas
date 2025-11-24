from pydantic import BaseModel
from .base import ORMBase


class ApiKeyCreate(BaseModel):
    name: str | None = None


class ApiKeyResponse(ORMBase):
    user_id: int
    key_hash: str
    name: str | None
    active: bool
    daily_limit: int
    used_today: int
    rate_limit_per_sec: int
