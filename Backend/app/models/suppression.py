from sqlalchemy import (
    String,
    Integer,
    Boolean,
    Text,
    ForeignKey,
    DateTime,
    Index
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.db import Base
from backend.app.models.base import IdMixin, TimestampMixin


class Suppression(Base, IdMixin, TimestampMixin):
    """
    Stores suppressed (blocked) emails/domains.
    Useful for:
    - preventing re-verification of known bounces/complaints
    - user-level suppression lists
    - team-level suppression lists
    - global suppression (admin only)
    """

    __tablename__ = "suppressions"

    # --------------------------------------
    # Ownership (optional)
    # --------------------------------------
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        index=True,
        nullable=True
    )

    team_id: Mapped[int | None] = mapped_column(
        ForeignKey("teams.id", ondelete="SET NULL"),
        index=True,
        nullable=True
    )

    user = relationship("User", back_populates="suppressions", lazy="joined")
    team = relationship("Team", back_populates="suppressions", lazy="joined")

    # --------------------------------------
    # Suppressed Target
    # --------------------------------------
    email: Mapped[str | None] = mapped_column(
        String(320),
        index=True,
        nullable=True
    )

    domain: Mapped[str | None] = mapped_column(
        String(255),
        index=True,
        nullable=True
    )

    # one of: "bounce", "complaint", "manual", "spamtrap", "unsubscribe", etc.
    reason: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True
    )

    # Optional notes / debugging payload
    details: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Optional expiration (e.g., 30-day temporary suppression)
    expires_at: Mapped[DateTime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True
    )

    # Whether this suppression applies globally by admin
    is_global: Mapped[bool] = mapped_column(Boolean, default=False)

    __table_args__ = (
        Index("idx_supp_email_user", "email", "user_id"),
        Index("idx_supp_domain_user", "domain", "user_id"),
        Index("idx_supp_email_team", "email", "team_id"),
        Index("idx_supp_expires", "expires_at"),
    )

    def __repr__(self):
        return (
            f"<Suppression id={self.id} email={self.email} domain={self.domain} "
            f"user={self.user_id} team={self.team_id} reason={self.reason}>"
  )
