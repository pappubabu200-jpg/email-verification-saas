# backend/app/models/bulk_job.py
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text
from sqlalchemy.sql import func
from backend.app.db import Base
from backend.app.models.base import IdMixin, TimestampMixin

class BulkJob(Base, IdMixin, TimestampMixin):
    __tablename__ = "bulk_jobs"

    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    job_id = Column(String(128), nullable=False, unique=True, index=True)
    status = Column(String(50), default="queued", index=True)  # queued, running, completed, failed, cancelled
    input_path = Column(String(1024), nullable=True)
    output_path = Column(String(1024), nullable=True)
    total = Column(Integer, default=0)
    processed = Column(Integer, default=0)
    valid = Column(Integer, default=0)
    invalid = Column(Integer, default=0)
    error_message = Column(Text, nullable=True)
    webhook_url = Column(String(1024), nullable=True)
