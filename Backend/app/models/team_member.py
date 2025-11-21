# backend/app/models/team_member.py
from sqlalchemy import Column, Integer, String, ForeignKey, Boolean
from backend.app.db import Base
from backend.app.models.base import IdMixin, TimestampMixin

class TeamMember(Base, IdMixin, TimestampMixin):
    __tablename__ = "team_members"
    team_id = Column(Integer, ForeignKey("teams.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    role = Column(String(50), default="member")
    active = Column(Boolean, default=True)
