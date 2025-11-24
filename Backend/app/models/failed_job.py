from sqlalchemy import (
    Integer,
    String,
    Text,
    DateTime,
    ForeignKey,
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func
from backend.app.db import Base
from backend.app.models.base import IdMixin


class FailedJob(Base, IdMixin):
    """
    Stores failures for bulk jobs, extractor jobs, or webhook processing.
    """

    __tablename__ = "failed_jobs"

    job_type: Mapped[str] = mapped_column(String(100), nullable=False)
    job_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    error_message: Mapped[str] = mapped_column(Text, nullable=False)
    trace: Mapped[str | None] = mapped_column(Text, nullable=True)

    attempts: Mapped[int] = mapped_column(Integer, default=0)

    occurred_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        index=True
    )

    related_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"),
        nullable=True,
        index=True
    )

    def __repr__(self):
        return f"<FailedJob type={self.job_type} attempts={self.attempts}>"
