from sqlalchemy import (
    Integer,
    String,
    Text,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from backend.app.db import Base
from backend.app.models.base import IdMixin, TimestampMixin


class WebhookEvent(Base, IdMixin, TimestampMixin):
    """
    Represents a single webhook delivery attempt.
    Similar to Stripe's Event Delivery logs.

    Stores:
    - event type
    - JSON payload
    - delivery outcome
    - retry count
    - HTTP response details
    """

    __tablename__ = "webhook_events"

    # --------------------------------------
    # Link to Webhook Endpoint
    # --------------------------------------
    endpoint_id: Mapped[int] = mapped_column(
        ForeignKey("webhook_endpoints.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    endpoint = relationship("WebhookEndpoint", back_populates="events_sent")

    # --------------------------------------
    # Event Metadata
    # --------------------------------------
    provider: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True
    )
    """
    Example:
        "system"
        "verification"
        "bulkjob"
        "billing"
    """

    event_type: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
        index=True
    )
    """
    Example:
        "verification.completed"
        "bulkjob.finished"
        "user.login"
        "subscription.renewed"
    """

    payload: Mapped[str | None] = mapped_column(
        Text,
        nullable=True
    )  # Raw JSON data

    # --------------------------------------
    # Delivery Info
    # --------------------------------------
    delivered: Mapped[bool] = mapped_column(Boolean, default=False)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)

    response_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    response_body: Mapped[str | None] = mapped_column(Text, nullable=True)

    delivered_at: Mapped[DateTime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True
    )

    failed_at: Mapped[DateTime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True
    )

    __table_args__ = (
        Index("idx_webhook_event_type", "event_type"),
        Index("idx_webhook_endpoint_delivery", "endpoint_id", "delivered"),
    )

    def __repr__(self):
        return f"<WebhookEvent id={self.id} type={self.event_type} delivered={self.delivered}>"
