
from sqlalchemy import Column, Integer, DateTime
from sqlalchemy.sql import func
from backend.app.db import Base as _Base

# Provide convenient mixins for models
class IdMixin:
    id = Column(Integer, primary_key=True, index=True)

class TimestampMixin:
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
