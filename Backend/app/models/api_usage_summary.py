from sqlalchemy import (
    Integer,
    String,
    Date,
    ForeignKey,
    Numeric,
    Index
)
from sqlalchemy.orm import Mapped, mapped_column
from backend.app.db import Base
from backend.app.models.base import IdMixin


class ApiUsageSummary(Base, IdMixin):
    """
    Daily/monthly aggregated API usage for billing + analytics.
    """

    __tablename__ = "api_usage_summary"

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    team_id: Mapped[int | None] = mapped_column(
        ForeignKey("teams.id", ondelete="SET NULL"),
        nullable=True,
        index=True
    )

    date: Mapped[Date] = mapped_column(Date, nullable=False, index=True)

    total_requests: Mapped[int] = mapped_column(Integer, default=0)
    total_verifications: Mapped[int] = mapped_column(Integer, default=0)
    total_bulk_processed: Mapped[int] = mapped_column(Integer, default=0)

    cost: Mapped[float] = mapped_column(Numeric(10, 2), default=0)

    __table_args__ = (
        Index("idx_usage_summary_user_date", "user_id", "date"),
        Index("idx_usage_summary_team_date", "team_id", "date"),
    )

    def __repr__(self):
        return f"<ApiUsageSummary user={self.user_id} date={self.date}>"
