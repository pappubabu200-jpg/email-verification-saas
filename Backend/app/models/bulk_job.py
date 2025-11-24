from sqlalchemy import (
    Column,
    Integer,
    String,
    Text,
    ForeignKey,
    Numeric,
    Boolean,
    DateTime,
    Index
)
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship, Mapped, mapped_column

from backend.app.db import Base
from backend.app.models.base import IdMixin, TimestampMixin


class BulkJob(Base, IdMixin, TimestampMixin):
    """
    Represents a bulk email verification job.
    Supports:
    - User jobs
    - Team jobs
    - Status tracking
    - File paths (S3/local)
    - Webhook callback
    - Cost estimate
    """

    __tablename__ = "bulk_jobs"

    # --------------------------------------
    # Ownership
    # --------------------------------------
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False
    )

    team_id: Mapped[int | None] = mapped_column(
        ForeignKey("teams.id", ondelete="SET NULL"),
        index=True,
        nullable=True
    )

    # Relationships
    user = relationship("User", back_populates="bulk_jobs")
    team = relationship("Team", back_populates="bulk_jobs")

    # --------------------------------------
    # Job identifiers
    # --------------------------------------
    job_id: Mapped[str] = mapped_column(
        String(128),
        unique=True,
        index=True,
        nullable=False
    )

    status: Mapped[str] = mapped_column(
        String(50),
        default="queued",
        index=True
    )
    # queued, running, completed, failed, cancelled

    # --------------------------------------
    # File paths (local or S3)
    # --------------------------------------
    input_path: Mapped[str | None] = mapped_column(
        Text,
        nullable=True
    )
    output_path: Mapped[str | None] = mapped_column(
        Text,
        nullable=True
    )

    # --------------------------------------
    # Stats
    # --------------------------------------
    total: Mapped[int] = mapped_column(Integer, default=0)
    processed: Mapped[int] = mapped_column(Integer, default=0)
    valid: Mapped[int] = mapped_column(Integer, default=0)
    invalid: Mapped[int] = mapped_column(Integer, default=0)

    # --------------------------------------
    # Errors / Webhooks
    # --------------------------------------
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    webhook_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)

    # --------------------------------------
    # Billing
    # --------------------------------------
    estimated_cost: Mapped[float | None] = mapped_column(
        Numeric(18, 6),
        nullable=True
    )

    # Optional timestamps for job execution
    started_at: Mapped[DateTime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[DateTime | None] = mapped_column(DateTime, nullable=True)

    __table_args__ = (
        Index("idx_bulkjob_status_user", "status", "user_id"),
        Index("idx_bulkjob_status_team", "status", "team_id"),
    )

    def __repr__(self):
        return f"<BulkJob id={self.id} job_id={self.job_id} status={self.status}>"
