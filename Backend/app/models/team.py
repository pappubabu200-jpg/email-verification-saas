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
    - Supports bulk verification jobs
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

    stripe_customer_id: Mapped[str | None] = mapped_column(String(255), nullable=True)

    settings: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # ------------------------------------
    # Relationships
    # ------------------------------------

    owner = relationship("User", back_populates="teams")

    members = relationship(
        "TeamMember",
        back_populates="team",
        cascade="all, delete-orphan"
    )

    audit_logs = relationship(
        "AuditLog",
        back_populates="team",
        cascade="all, delete-orphan"
    )

    credit_transactions = relationship(
        "TeamCreditTransaction",
        back_populates="team",
        cascade="all, delete-orphan"
    )

    balance = relationship(
        "TeamBalance",
        back_populates="team",
        cascade="all, delete-orphan",
        uselist=False
    )

    # Bulk verification jobs (team level)
    bulk_jobs = relationship(
        "BulkJob",
        back_populates="team",
        cascade="all, delete-orphan"
    )

    # Team credit reservations
    credit_reservations = relationship(
        "CreditReservation",
        back_populates="team",
        cascade="all, delete-orphan"
    )
    extractor_jobs = relationship(
    "ExtractorJob",
    back_populates="team",
    cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("idx_team_active_owner", "owner_id", "is_active"),
    )

    def __repr__(self):
        return f"<Team id={self.id} name='{self.name}' owner={self.owner_id}>"
