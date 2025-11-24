from .base import ORMBase
from pydantic import BaseModel
from datetime import datetime


class SubscriptionResponse(ORMBase):
    user_id: int
    plan_id: int | None
    status: str
    price_amount: float | None
    price_interval: str
    stripe_subscription_id: str
    stripe_customer_id: str
    current_period_start: datetime | None
    current_period_end: datetime | None
