from sqlalchemy import Column, Integer, String, ForeignKey, Boolean
from sqlalchemy.orm import relationship
from backend.app.db import Base
from backend.app.models.base import IdMixin, TimestampMixin

# Supported roles
TEAM_ROLES = ("owner", "admin", "member", "viewer")

class TeamMember(Base, IdMixin, TimestampMixin):
    __tablename__ = "team_members"

    team_id = Column(Integer, ForeignKey("teams.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    role = Column(String(50), default="member")
    invited = Column(Boolean, default=False)

    team = relationship("Team", back_populates="members")
