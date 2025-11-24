from sqlalchemy import (
    Integer,
    String,
    Text,
    ForeignKey,
    DateTime,
    Index
)
from sqlalchemy.orm import relationship, Mapped, mapped_column

from backend.app.db import Base
from backend.app.models.base import IdMixin, TimestampMixin


class ExtractorJob(Base, IdMixin, TimestampMixin):
    """
    Represents a data extraction job.
    Example: Extract emails/domains/names from large files before bulk verification.
    Supports:
    - User jobs
    - Team jobs
    - Job status tracking
    - Input/Output file paths (S3/local)
    """

    __tablename__ = "extractor_jobs"

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
    user = relationship("User", back_populates="extractor_jobs")
    team = relationship("Team", back_populates="extractor_jobs")

    # --------------------------------------
    # Job Info
    # --------------------------------------
    job_id: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        unique=True,
        index=True
    )

    status: Mapped[str] = mapped_column(
        String(50),
        default="queued",
        index=True
    )
    # queued, running, completed, failed, cancelled

    input_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    output_path: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # --------------------------------------
    # Progress Metrics
    # --------------------------------------
    total: Mapped[int] = mapped_column(Integer, default=0)
    processed: Mapped[int] = mapped_column(Integer, default=0)

    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Optional: when job starts and ends
    started_at: Mapped[DateTime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[DateTime | None] = mapped_column(DateTime, nullable=True)

    __table_args__ = (
        Index("idx_extractor_status_user", "status", "user_id"),
        Index("idx_extractor_status_team", "status", "team_id"),
    )

    def __repr__(self):
        return f"<ExtractorJob id={self.id} job_id={self.job_id} status={self.status}>"
