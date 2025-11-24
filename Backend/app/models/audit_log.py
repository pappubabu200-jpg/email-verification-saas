from sqlalchemy import (
    Column,
    String,
    Integer,
    ForeignKey,
    JSON,
    Index,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.db import Base
from backend.app.models.base import IdMixin, TimestampMixin


class AuditLog(Base, IdMixin, TimestampMixin):
    """
    Stores audit trails for every important action:
    - login events
    - API key usage
    - credit changes
    - webhook triggers
    - email verification events
    - admin actions
    """

    __tablename__ = "audit_logs"

    # Who performed the action?
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )

    team_id: Mapped[int | None] = mapped_column(
        ForeignKey("teams.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )

    # Type of event: "login", "logout", "api_call", "credit_used", "admin_update", etc.
    event_type: Mapped[str] = mapped_column(String(64), index=True, nullable=False)

    # Human-readable message
    message: Mapped[str] = mapped_column(String(512), nullable=False)

    # IP address of request
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # Optional request identifier for debugging microservices
    request_id: Mapped[str | None] = mapped_column(String(100), index=True)

    # JSON metadata (very powerful)
    meta: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Relationships
    user = relationship("User", back_populates="audit_logs")
    team = relationship("Team", back_populates="audit_logs")

    __table_args__ = (
        Index("idx_audit_event_user", "event_type", "user_id"),
        Index("idx_audit_event_team", "event_type", "team_id"),
    )

    def __repr__(self):
        return f"<AuditLog id={self.id} event={self.event_type} user={self.user_id}>"
