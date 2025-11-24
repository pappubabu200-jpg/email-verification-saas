from .base import ORMBase
from pydantic import BaseModel
from datetime import date


class ApiUsageSummaryResponse(ORMBase):
    user_id: int
    team_id: int | None
    date: date
    total_requests: int
    total_verifications: int
    total_bulk_processed: int
    cost: float
