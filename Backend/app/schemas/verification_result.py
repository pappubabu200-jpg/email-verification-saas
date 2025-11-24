from .base import ORMBase
from pydantic import BaseModel


class VerificationResultResponse(ORMBase):
    user_id: int
    email: str
    status: str
    reason: str | None
    domain: str | None
    score: float | None
