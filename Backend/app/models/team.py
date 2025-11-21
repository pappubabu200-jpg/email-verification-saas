from sqlalchemy import Column, Integer, String, ForeignKey
from sqlalchemy.orm import relationship
from backend.app.db import Base
from backend.app.models.base import IdMixin, TimestampMixin

class Team(Base, IdMixin, TimestampMixin):
    __tablename__ = "teams"

    name = Column(String(255), nullable=False)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    # relationships
    members = relationship("TeamMember", back_populates="team", cascade="all, delete-orphan")
