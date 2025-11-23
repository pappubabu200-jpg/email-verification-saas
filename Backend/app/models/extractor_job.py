from sqlalchemy import Column, Integer, String, Text, ForeignKey
from backend.app.db import Base
from backend.app.models.base import IdMixin, TimestampMixin

class ExtractorJob(Base, IdMixin, TimestampMixin):
    __tablename__ = "extractor_jobs"

    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    job_id = Column(String(128), nullable=False, unique=True, index=True)

    status = Column(String(50), default="queued")
    input_path = Column(String(500))
    output_path = Column(String(500))

    total = Column(Integer, default=0)
    processed = Column(Integer, default=0)
    error_message = Column(Text, nullable=True)

    # NEW
    team_id = Column(Integer, nullable=True, index=True)
