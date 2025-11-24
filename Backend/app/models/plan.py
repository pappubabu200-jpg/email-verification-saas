from sqlalchemy import Column, String, Integer, Numeric, Boolean
from backend.app.db import Base
from backend.app.models.base import IdMixin, TimestampMixin

class Plan(Base, IdMixin, TimestampMixin):
    __tablename__ = "plans"

    name = Column(String(100), unique=True, nullable=False)
    display_name = Column(String(200), nullable=False)
    monthly_price_usd = Column(Numeric(10,2), default=0)
    daily_search_limit = Column(Integer, default=0)       # 0 == unlimited
    monthly_credit_allowance = Column(Integer, default=0) # credits included monthly
    rate_limit_per_sec = Column(Integer, default=0)       # 0 == use global default
    is_public = Column(Boolean, default=True)
# backend/app/models/plan.py
from sqlalchemy import Column, String, Integer, Numeric, Boolean
from backend.app.db import Base
try:
    from backend.app.models.base import IdMixin, TimestampMixin
except Exception:
    # Minimal fallback if your base mixins don't exist
    class IdMixin:
        id = Column(Integer, primary_key=True, index=True)
    class TimestampMixin:
        pass

class Plan(Base, IdMixin, TimestampMixin):
    __tablename__ = "plans"

    name = Column(String(100), unique=True, nullable=False)
    display_name = Column(String(200), nullable=False)
    monthly_price_usd = Column(Numeric(10, 2), default=0)
    daily_search_limit = Column(Integer, default=0)       # 0 == unlimited
    monthly_credit_allowance = Column(Integer, default=0) # credits included monthly
    rate_limit_per_sec = Column(Integer, default=0)       # 0 == use global default
    is_public = Column(Boolean, default=True)
