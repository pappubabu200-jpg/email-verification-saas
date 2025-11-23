from sqlalchemy import Column, Integer, String, Numeric, ForeignKey
from backend.app.db import Base
from backend.app.models.base import IdMixin, TimestampMixin

class Team(Base, IdMixin, TimestampMixin):
    __tablename__ = "teams"

    name = Column(String(255), nullable=False)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    credits = Column(Numeric(18, 6), nullable=False, server_default="0")
# backend/app/models/team.py
from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, Numeric
from backend.app.db import Base
from app.models.base import IdMixin, TimestampMixin  # adjust import if your base path differs

class Team(Base, IdMixin, TimestampMixin):
    __tablename__ = "teams"

    name = Column(String(200), nullable=False, unique=True)
    owner_user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    credits = Column(Numeric(18,6), default=0)  # team credit pool
    is_active = Column(Boolean, default=True)

# backend/app/models/team.py
from sqlalchemy import Column, Integer, String, Text, Boolean, ForeignKey
from backend.app.db import Base
from backend.app.models.base import IdMixin, TimestampMixin
from sqlalchemy.orm import relationship

class Team(Base, IdMixin, TimestampMixin):
    __tablename__ = "teams"
    name = Column(String(255), nullable=False, unique=True)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    credits = Column(Integer, default=0)  # team shared credits
    stripe_customer_id = Column(String(255), nullable=True)
    metadata = Column(Text, nullable=True)

    members = relationship("TeamMember", back_populates="team")

