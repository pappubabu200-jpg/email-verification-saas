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

# backend/app/models/team.py
from sqlalchemy import Column, Integer, String, Text, Boolean, ForeignKey, Numeric
from backend.app.db import Base
from backend.app.models.base import IdMixin, TimestampMixin

class Team(Base, IdMixin, TimestampMixin):
    __tablename__ = "teams"
    name = Column(String(200), unique=True, nullable=False)
    slug = Column(String(200), unique=True, nullable=True)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    metadata = Column(Text, nullable=True)
    credits = Column(Numeric(18,6), default=0)  # team pool balance
    is_active = Column(Boolean, default=True)
from sqlalchemy import Column, Integer, String, Boolean, Numeric, ForeignKey, DateTime
from sqlalchemy.sql import func
from backend.app.db import Base
from backend.app.models.base import IdMixin, TimestampMixin

class Team(Base, IdMixin, TimestampMixin):
    __tablename__ = "teams"
    name = Column(String(200), unique=True, nullable=False)
    owner_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    credits = Column(Numeric(18,6), nullable=False, default=0)
    is_active = Column(Boolean, default=True)
