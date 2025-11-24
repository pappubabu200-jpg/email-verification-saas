from sqlalchemy import (
    Integer,
    String,
    ForeignKey,
    DateTime,
    Index
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from backend.app.db import Base
from backend.app.models.base import IdMixin


class UsageLog(Base, IdMixin):
    """
    Records every API usage event:
    - which user made the request
    - which API key was used
    - endpoint + method
    - HTTP status code
    - IP + user agent
    - timestamp
    """

    __tablename__ = "usage_logs"

    # --------------------------------------
    # Ownership
    # --------------------------------------
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False
    )

    api_key_id: Mapped[int | None] = mapped_column(
        ForeignKey("api_keys.id", ondelete="SET NULL"),
        index=True,
        nullable=True
    )

    user = relationship("User", back_populates="usage_logs")
    api_key = relationship("ApiKey", back_populates="usage_logs")

    # --------------------------------------
    # Request Info
    # --------------------------------------
    endpoint: Mapped[str] = mapped_column(
        String(255),
        nullable=False
    )

    method: Mapped[str] = mapped_column(
        String(20),
        nullable=False
    )

    status_code: Mapped[int] = mapped_column(
        Integer,
        nullable=False
    )

    ip: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True
    )

    user_agent: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True
    )

    # --------------------------------------
    # Timestamp
    # --------------------------------------
    created_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        index=True
    )

    __table_args__ = (
        Index("idx_usage_user_time", "user_id", "created_at"),
        Index("idx_usage_api_key_time", "api_key_id", "created_at"),
    )

    def __repr__(self):
        return f"<UsageLog id={self.id} user={self.user_id} endpoint={self.endpoint}>"
