from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.sql import func
from backend.app.db import Base

class UsageLog(Base):
    __tablename__ = "usage_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=False)
    api_key_id = Column(Integer, ForeignKey("api_keys.id"), index=True)
    endpoint = Column(String(255), nullable=False)
    method = Column(String(20), nullable=False)
    status_code = Column(Integer, nullable=False)
    ip = Column(String(100), nullable=True)
    user_agent = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
