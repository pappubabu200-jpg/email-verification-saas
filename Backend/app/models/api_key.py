from sqlalchemy import Column, String, Boolean, Integer, ForeignKey, Numeric
from backend.app.db import Base
from backend.app.models.base import IdMixin, TimestampMixin

class ApiKey(Base, IdMixin, TimestampMixin):
    __tablename__ = "api_keys"

    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    key = Column(String(128), unique=True, index=True, nullable=False)
    name = Column(String(255), nullable=True)
    active = Column(Boolean, default=True)
    daily_limit = Column(Integer, default=5000)     # per key per day
    used_today = Column(Integer, default=0)         # reset at midnight

    # NEW: per-api-key RPS limiter (optional)
    rate_limit_per_sec = Column(Integer, default=0)  # 0 => use global default; >0 => per-api-key RPS

    def __repr__(self):
        return f"<ApiKey id={self.id} user_id={self.user_id} active={self.active}>"
