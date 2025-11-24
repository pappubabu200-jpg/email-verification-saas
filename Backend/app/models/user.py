from sqlalchemy import (
    Column,
    Integer,
    String,
    Boolean,
    Numeric,
    Index,
)
from sqlalchemy.orm import relationship, Mapped, mapped_column

from backend.app.db import Base
from backend.app.models.base import IdMixin, TimestampMixin


class User(Base, IdMixin, TimestampMixin):
    """
    Core user model for the SaaS platform.
    Includes:
    - authentication
    - billing identity
    - subscription
    - credits
    - team membership
    - auditing
    """

    __tablename__ = "users"

    # -----------------------------
    # Authentication
    # -----------------------------
    email: Mapped[str] = mapped_column(
        String(255), unique=True, index=True, nullable=False
    )

    hashed_password: Mapped[str] = mapped_column(
        String(255), nullable=False
    )

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    email_verified: Mapped[bool] = mapped_column(Boolean, default=False)

    # -----------------------------
    # User Identity
    # -----------------------------
    first_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    last_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    country: Mapped[str | None] = mapped_column(String(100), nullable=True)
    timezone: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # -----------------------------
    # Subscription / Billing
    # -----------------------------
    plan: Mapped[str | None] = mapped_column(
        String(100), index=True, nullable=True
    )  # free / pro / enterprise

    credits: Mapped[float] = mapped_column(
        Numeric(18, 2),
        nullable=False,
        server_default="0"
    )

    stripe_customer_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True
    )

    last_login_at: Mapped[str | None] = mapped_column(
        String(50), nullable=True
    )
    last_login_ip: Mapped[str | None] = mapped_column(
        String(50), nullable=True
    )

    # -----------------------------
    # Relationships
    # -----------------------------

    # API Keys
    api_keys = relationship(
        "ApiKey",
        back_populates="user",
        cascade="all, delete-orphan"
    )

    # User’s audit logs
    audit_logs = relationship(
        "AuditLog",
        back_populates="user",
        cascade="all, delete-orphan"
    )

    # User’s subscription
    subscriptions = relationship(
        "Subscription",
        back_populates="user",
        cascade="all, delete-orphan"
    )

    # Usage logs (verification events)
    usage_logs = relationship(
        "UsageLog",
        back_populates="user",
        cascade="all, delete-orphan"
    )

    # Credit transactions (debits/credits)
    credit_transactions = relationship(
        "CreditTransaction",
        back_populates="user",
        cascade="all, delete-orphan"
    )

    # Team relationship (if user is part of a team)
    teams = relationship(
        "TeamMember",
        back_populates="user",
        cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("idx_user_email_active", "email", "is_active"),
    )

    def __repr__(self):
        return f"<User id={self.id} email='{self.email}' active={self.is_active}>"
