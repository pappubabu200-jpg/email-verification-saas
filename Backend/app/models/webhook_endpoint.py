from sqlalchemy import (
    String,
    Integer,
    Boolean,
    ForeignKey,
    DateTime,
    Text,
    Index,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from backend.app.db import Base
from backend.app.models.base import IdMixin, TimestampMixin


class WebhookEndpoint(Base, IdMixin, TimestampMixin):
    """
    Represents a webhook endpoint that receives event notifications.
    Similar design to Stripe Webhook Endpoints.

    Supports:
    - user-level or team-level ownership
    - event filtering (e.g., verification.completed, bulkjob.finished)
    - secret signature key
    - versioning
    - active/inactive control
    """

    __tablename__ = "webhook_endpoints"

    # --------------------------------------
    # Ownership (User or Team)
    # --------------------------------------
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True,
        index=True
    )

    team_id: Mapped[int | None] = mapped_column(
        ForeignKey("teams.id", ondelete="CASCADE"),
        nullable=True,
        index=True
    )

    user = relationship("User")
    team = relationship("Team")

    # --------------------------------------
    # Endpoint Configuration
    # --------------------------------------
    url: Mapped[str] = mapped_column(
        String(1024),
        nullable=False
    )

    description: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True
    )

    # Secret key for signing webhook payloads (HMAC)
    secret: Mapped[str] = mapped_column(
        String(255),
        nullable=False
    )

    # Comma-separated list of events the endpoint subscribes to
    """
    Examples:
        "verification.completed,bulkjob.finished"
        "user.login"
        "all"
    """
    events: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="all"
    )

    # Activate/Deactivate without deleting
    active: Mapped[bool] = mapped_column(Boolean, default=True)

    # Optional API versioning for webhooks
    api_version: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True
    )

    # --------------------------------------
    # Last Delivery State
    # --------------------------------------
    last_success_at: Mapped[DateTime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True
    )

    last_failure_at: Mapped[DateTime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True
    )

    last_status_code: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True
    )

    # --------------------------------------
    # Relationship to Webhook Events
    # --------------------------------------
    events_sent = relationship(
        "WebhookEvent",
        back_populates="endpoint",
        cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("idx_webhook_user_active", "user_id", "active"),
        Index("idx_webhook_team_active", "team_id", "active"),
    )

    def __repr__(self):
        return f"<WebhookEndpoint id={self.id} url='{self.url}' active={self.active}>"
