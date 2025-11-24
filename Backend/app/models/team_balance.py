from sqlalchemy import (
    Integer,
    Numeric,
    ForeignKey,
    Index
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.db import Base
from backend.app.models.base import IdMixin, TimestampMixin


class TeamBalance(Base, IdMixin, TimestampMixin):
    """
    Tracks the total available credit balance for each team.
    One Team → One TeamBalance record.
    """

    __tablename__ = "team_balances"

    # --------------------------------------
    # Team Link (1:1 relationship)
    # --------------------------------------
    team_id: Mapped[int] = mapped_column(
        ForeignKey("teams.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True
    )

    team = relationship("Team", back_populates="balance")

    # --------------------------------------
    # Current Balance
    # --------------------------------------
    balance: Mapped[float] = mapped_column(
        Numeric(18, 6),
        nullable=False,
        default=0
    )

    __table_args__ = (
        Index("idx_team_balance_team", "team_id"),
    )

    def __repr__(self):
        return f"<TeamBalance team={self.team_id} balance={self.balance}>"
