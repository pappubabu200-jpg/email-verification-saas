from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean
from sqlalchemy.sql import func
from backend.app.db import Base

class WebhookDLQ(Base):
    __tablename__ = "webhook_dlq"

    id = Column(Integer, primary_key=True)
    url = Column(String(500), nullable=False)
    payload = Column(Text, nullable=False)
    headers = Column(Text, nullable=True)

    error_message = Column(Text, nullable=True)
    attempts = Column(Integer, default=0)
    resolved = Column(Boolean, default=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
