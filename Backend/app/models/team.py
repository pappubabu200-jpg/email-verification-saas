# backend/app/models/team.py
from sqlalchemy import Column, Integer, String, Text, Boolean, ForeignKey
from backend.app.db import Base
from backend.app.models.base import IdMixin, TimestampMixin

class Team(Base, IdMixin, TimestampMixin):
    __tablename__ = "teams"
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    slug = Column(String(255), nullable=False, unique=True)
    description = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True)
