
from sqlalchemy import (
    Column,
    Integer,
    String,
    Boolean,
    ForeignKey,
    Numeric,
    JSON,
    Index,
)
from sqlalchemy.orm import relationship, Mapped, mapped_column

from backend.app.db import Base
from backend.app.models.base import IdMixin, TimestampMixin


class Team(Base, IdMixin, TimestampMixin):
    """
    Represents a team account.
    - Has an owner (User)
    - Holds shared credits
    - Has multiple members
    - Supports audit logs
    - Supports billing (Stripe)
    """

    __tablename__ = "teams"

    # ------------------------------------
    # Basic Info
    # ------------------------------------
    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        unique=True,
        index=True
    )

    # Owner user
    owner_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # ------------------------------------
    # Billing & Credits
    # ------------------------------------
    credits: Mapped[float] = mapped_column(
        Numeric(18, 2),
        nullable=False,
        server_default="0"
    )

    stripe_customer_id: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True
    )

    # Additional optional metadata
    settings: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # ------------------------------------
    # Relationships
    # ------------------------------------

    # Team owner (User)
    owner = relationship("User", back_populates="teams")

    # Members list
    members = relationship(
        "TeamMember",
        back_populates="team",
        cascade="all, delete-orphan"
    )

    # Team audit logs
    audit_logs = relationship(
        "AuditLog",
        back_populates="team",
        cascade="all, delete-orphan"
    )

    # Team credit transactions
    credit_transactions = relationship(
        "TeamCreditTransaction",
        back_populates="team",
        cascade="all, delete-orphan"
    )

    # Team balance table (if your schema uses it)
    balance = relationship(
        "TeamBalance",
        back_populates="team",
        cascade="all, delete-orphan",
        uselist=False  # single balance record
    )

    __table_args__ = (
        Index("idx_team_active_owner", "owner_id", "is_active"),
    )

    def __repr__(self):
        return f"<Team id={self.id} name='{self.name}' owner={self.owner_id}>"
