from .base import ORMBase
from pydantic import BaseModel


class PlanBase(BaseModel):
    name: str
    display_name: str
    monthly_price_usd: float
    daily_search_limit: int
    monthly_credit_allowance: int
    rate_limit_per_sec: int
    is_public: bool


class PlanResponse(ORMBase, PlanBase):
    pass
