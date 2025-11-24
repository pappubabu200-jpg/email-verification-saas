from .base import ORMBase
from datetime import datetime


class CreditReservationResponse(ORMBase):
    user_id: int
    amount: float
    job_id: str | None
    locked: bool
    expires_at: datetime | None
    reference: str | None
