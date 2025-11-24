from pydantic import BaseModel
from .base import ORMBase


class TeamBase(BaseModel):
    name: str
    is_active: bool = True
    credits: float | None = 0
    stripe_customer_id: str | None = None


class TeamCreate(BaseModel):
    name: str


class TeamResponse(ORMBase, TeamBase):
    owner_id: int
