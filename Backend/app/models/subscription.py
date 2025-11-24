from sqlalchemy import (
    Integer,
    String,
    Boolean,
    Numeric,
    DateTime,
    ForeignKey,
    Text,
    Index,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.db import Base
from backend.app.models.base import IdMixin, TimestampMixin


class Subscription(Base, IdMixin, TimestampMixin):
    """
    User subscription tied to Stripe Billing.
    Stores:
    - stripe_subscription_id
    - plan_id (internal plan)
    - billing cycle
    - renewal period
    - cancellation
    - raw webhook payloads
    """

    __tablename__ = "subscriptions"

    # ----------------------------------------
    # Stripe Identifiers
    # ----------------------------------------
    stripe_subscription_id: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        index=True,
        nullable=False
    )

    stripe_customer_id: Mapped[str] = mapped_column(
        String(255),
        index=True,
        nullable=False
    )

    stripe_price_id: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True
    )

    stripe_product_id: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True
    )

    # ----------------------------------------
    # Ownership
    # ----------------------------------------
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False
    )

    user = relationship("User", back_populates="subscriptions")

    # ----------------------------------------
    # Plan Link (INTERNAL PLAN SYSTEM)
    # ----------------------------------------
    plan_id: Mapped[int | None] = mapped_column(
        ForeignKey("plans.id", ondelete="SET NULL"),
        nullable=True,
        index=True
    )

    plan = relationship("Plan", back_populates="subscriptions")

    # ----------------------------------------
    # Billing Details
    # ----------------------------------------
    price_amount: Mapped[float | None] = mapped_column(
        Numeric(10, 2),
        nullable=True
    )  # USD

    price_interval: Mapped[str] = mapped_column(
        String(20),
        default="month"
    )  # month or year

    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True
    )
    # active, canceled, incomplete, past_due, trialing

    cancel_at_period_end: Mapped[bool] = mapped_column(Boolean, default=False)

    # ----------------------------------------
    # Renewal Dates
    # ----------------------------------------
    current_period_start: Mapped[DateTime | None] = mapped_column(
        DateTime(timezone=True)
    )

    current_period_end: Mapped[DateTime | None] = mapped_column(
        DateTime(timezone=True)
    )

    canceled_at: Mapped[DateTime | None] = mapped_column(
        DateTime(timezone=True)
    )

    # ----------------------------------------
    # Raw Stripe Webhook Data (Optional)
    # ----------------------------------------
    raw: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        Index("idx_subscription_user_status", "user_id", "status"),
        Index("idx_subscription_plan_status", "plan_id", "status"),
    )

    def __repr__(self):
        return (
            f"<Subscription id={self.id} user={self.user_id} "
            f"plan={self.plan_id} status={self.status}>"
        )
