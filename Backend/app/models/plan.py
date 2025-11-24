from sqlalchemy import (
    String,
    Integer,
    Numeric,
    Boolean,
    Index
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.db import Base
from backend.app.models.base import IdMixin, TimestampMixin


class Plan(Base, IdMixin, TimestampMixin):
    """
    Subscription plans for SaaS billing.
    Examples: Free, Pro, Business, Enterprise
    """

    __tablename__ = "plans"

    # --------------------------------------
    # Identifiers
    # --------------------------------------
    name: Mapped[str] = mapped_column(
        String(100),
        unique=True,
        nullable=False,
        index=True
    )

    display_name: Mapped[str] = mapped_column(
        String(200),
        nullable=False
    )

    # --------------------------------------
    # Pricing
    # --------------------------------------
    monthly_price_usd: Mapped[float] = mapped_column(
        Numeric(10, 2),
        default=0
    )

    # --------------------------------------
    # Limits
    # --------------------------------------
    daily_search_limit: Mapped[int] = mapped_column(
        Integer,
        default=0
    )  # 0 = unlimited

    monthly_credit_allowance: Mapped[int] = mapped_column(
        Integer,
        default=0
    )  # included credits

    rate_limit_per_sec: Mapped[int] = mapped_column(
        Integer,
        default=0
    )  # 0 = global default

    # --------------------------------------
    # Visibility
    # --------------------------------------
    is_public: Mapped[bool] = mapped_column(Boolean, default=True)

    # --------------------------------------
    # Relationships
    # --------------------------------------
    subscriptions = relationship(
        "Subscription",
        back_populates="plan",
        cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("idx_plan_public_price", "is_public", "monthly_price_usd"),
    )

    def __repr__(self):
        return f"<Plan id={self.id} name='{self.name}' price=${self.monthly_price_usd}>"
