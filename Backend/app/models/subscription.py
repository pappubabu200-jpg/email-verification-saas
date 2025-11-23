
from sqlalchemy import Column, Integer, String, Boolean, Numeric, DateTime, ForeignKey
from sqlalchemy.sql import func
from backend.app.db import Base
from backend.app.models.base import IdMixin, TimestampMixin

class Subscription(Base, IdMixin, TimestampMixin):
    __tablename__ = "subscriptions"

    # Stripe Identifiers
    stripe_subscription_id = Column(String(255), unique=True, index=True, nullable=False)
    stripe_customer_id = Column(String(255), index=True, nullable=False)

    # Link to User
    user_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=False)

    # Pricing / Plan
    plan_name = Column(String(100), nullable=True)   # maps to your internal plan
    price_amount = Column(Numeric(10, 2), nullable=True)  # price in USD
    price_interval = Column(String(20), default="month")  # month/year

    # Status
    status = Column(String(50), nullable=False, index=True)
    cancel_at_period_end = Column(Boolean, default=False)

    # Dates
    current_period_start = Column(DateTime(timezone=True))
    current_period_end = Column(DateTime(timezone=True))

    # Raw webhook payload for debugging
    raw = Column(String)
