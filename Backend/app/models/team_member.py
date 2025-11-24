from sqlalchemy import (
    Integer,
    String,
    Boolean,
    ForeignKey,
    DateTime
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from backend.app.db import Base
from backend.app.models.base import IdMixin, TimestampMixin


TEAM_ROLES = ("owner", "admin", "member", "viewer")


class TeamMember(Base, IdMixin, TimestampMixin):
    """
    Represents membership of a user inside a team.
    Supports:
    - roles (owner/admin/member/viewer)
    - invitations
    - join timestamps
    - active/inactive state
    """

    __tablename__ = "team_members"

    # --------------------------------------
    # Foreign Keys
    # --------------------------------------
    team_id: Mapped[int] = mapped_column(
        ForeignKey("teams.id", ondelete="CASCADE"),
        index=True,
        nullable=False
    )

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False
    )

    # --------------------------------------
    # Member Data
    # --------------------------------------
    role: Mapped[str] = mapped_column(
        String(50),
        default="member",
        nullable=False
    )  # must be one of TEAM_ROLES

    invited: Mapped[bool] = mapped_column(Boolean, default=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True)

    joined_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now()
    )

    # --------------------------------------
    # Relationships
    # --------------------------------------
    team = relationship("Team", back_populates="members")
    user = relationship("User", back_populates="teams")

    def __repr__(self):
        return (
            f"<TeamMember id={self.id} team={self.team_id} "
            f"user={self.user_id} role={self.role} active={self.active}>"
        )
