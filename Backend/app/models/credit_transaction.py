from sqlalchemy import (
    Integer,
    Numeric,
    String,
    Text,
    ForeignKey,
    Index
)
from sqlalchemy.orm import relationship, Mapped, mapped_column

from backend.app.db import Base
from backend.app.models.base import IdMixin, TimestampMixin


class CreditTransaction(Base, IdMixin, TimestampMixin):
    """
    Record of credit usage:
    - amount positive = topup
    - amount negative = charge
    - supports both user and team billing
    """

    __tablename__ = "credit_transactions"

    # --------------------------------------
    # Ownership
    # --------------------------------------
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True
    )

    team_id: Mapped[int | None] = mapped_column(
        ForeignKey("teams.id", ondelete="SET NULL"),
        nullable=True,
        index=True
    )

    user = relationship("User", back_populates="credit_transactions")
    team = relationship("Team", back_populates="credit_transactions")

    # --------------------------------------
    # Transaction details
    # --------------------------------------
    amount: Mapped[float] = mapped_column(
        Numeric(18, 6),
        nullable=False
    )

    balance_after: Mapped[float] = mapped_column(
        Numeric(18, 6),
        nullable=False
    )

    type: Mapped[str] = mapped_column(
        String(50),
        nullable=False
    )  
    # examples: "topup", "charge", "refund", "bulk_job", "api_call"

    reference: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # avoid "metadata" keyword → replace with "details"
    details: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        Index("idx_credit_txn_user_type", "user_id", "type"),
        Index("idx_credit_txn_team_type", "team_id", "type"),
    )

    def __repr__(self):
        return (
            f"<CreditTransaction id={self.id} "
            f"user={self.user_id} team={self.team_id} "
            f"amount={self.amount} balance_after={self.balance_after}>"
        )
