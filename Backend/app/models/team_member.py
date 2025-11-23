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

# backend/app/models/team_member.py
from sqlalchemy import Column, Integer, String, ForeignKey, Boolean
from backend.app.db import Base
from backend.app.models.base import IdMixin, TimestampMixin

class TeamMember(Base, IdMixin, TimestampMixin):
    __tablename__ = "team_members"
    team_id = Column(Integer, ForeignKey("teams.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    role = Column(String(50), default="member")  # owner|admin|member
    is_active = Column(Boolean, default=True)

from sqlalchemy import Column, Integer, String, ForeignKey
from backend.app.db import Base
from backend.app.models.base import IdMixin, TimestampMixin

class TeamMember(Base, IdMixin, TimestampMixin):
    __tablename__ = "team_members"
    team_id = Column(Integer, ForeignKey("teams.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    role = Column(String(50), default="member", nullable=False)

# backend/app/models/team_member.py
from sqlalchemy import Column, Integer, String, ForeignKey, DateTime
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from backend.app.db import Base
from backend.app.models.base import IdMixin

class TeamMember(Base, IdMixin):
    __tablename__ = "team_members"

    team_id = Column(Integer, ForeignKey("teams.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    role = Column(String(50), nullable=True)
    joined_at = Column(DateTime(timezone=True), server_default=func.now())

    team = relationship("Team", back_populates="members", viewonly=True)
from sqlalchemy import Column, Integer, String, ForeignKey
from backend.app.db import Base
from backend.app.models.base import IdMixin, TimestampMixin

class TeamMember(Base, IdMixin, TimestampMixin):
    __tablename__ = "team_members"

    team_id = Column(Integer, ForeignKey("teams.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    role = Column(String(50), default="member")
