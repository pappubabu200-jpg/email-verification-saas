
# backend/app/models/webhook_event.py
from sqlalchemy import Column, Integer, Text, String, DateTime
from sqlalchemy.sql import func
from backend.app.db import Base

class WebhookEvent(Base):
    __tablename__ = "webhook_events"

    id = Column(Integer, primary_key=True, index=True)
    provider = Column(String(100), nullable=True)
    event_type = Column(String(200), nullable=True)
    payload = Column(Text, nullable=True)
    received_at = Column(DateTime(timezone=True), server_default=func.now())
