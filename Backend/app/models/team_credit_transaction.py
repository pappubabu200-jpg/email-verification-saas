from sqlalchemy import (
    Integer,
    Numeric,
    String,
    Text,
    ForeignKey,
    Index
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.db import Base
from backend.app.models.base import IdMixin, TimestampMixin


class TeamCreditTransaction(Base, IdMixin, TimestampMixin):
    """
    Tracks credit topups, debits, and adjustments for Team accounts.
    Works together with TeamBalance + CreditReservation systems.
    """

    __tablename__ = "team_credit_transactions"

    # --------------------------------------
    # Ownership
    # --------------------------------------
    team_id: Mapped[int] = mapped_column(
        ForeignKey("teams.id", ondelete="CASCADE"),
        index=True,
        nullable=False
    )
    team = relationship("Team", back_populates="credit_transactions")

    # --------------------------------------
    # Transaction values
    # --------------------------------------
    amount: Mapped[float] = mapped_column(
        Numeric(18, 6),
        nullable=False
    )  # positive = topup, negative = debit

    balance_after: Mapped[float] = mapped_column(
        Numeric(18, 6),
        nullable=False
    )

    # e.g., topup, debit, refund, transfer_in, transfer_out
    type: Mapped[str] = mapped_column(
        String(50),
        nullable=False
    )

    reference: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True
    )

    # SQLAlchemy reserved keyword → rename to details
    details: Mapped[str | None] = mapped_column(
        Text,
        nullable=True
    )

    __table_args__ = (
        Index("idx_team_credit_txn_team_type", "team_id", "type"),
    )

    def __repr__(self):
        return (
            f"<TeamCreditTransaction id={self.id} team={self.team_id} "
            f"amount={self.amount} balance_after={self.balance_after}>"
        )
