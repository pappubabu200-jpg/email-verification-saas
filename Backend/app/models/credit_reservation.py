from sqlalchemy import (
    Integer,
    Numeric,
    String,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
)
from sqlalchemy.orm import relationship, Mapped, mapped_column

from backend.app.db import Base
from backend.app.models.base import IdMixin, TimestampMixin


class CreditReservation(Base, IdMixin, TimestampMixin):
    """
    Temporary reservation of credits for:
    - bulk jobs
    - API verification batches
    - team usage
    """

    __tablename__ = "credit_reservations"

    # --------------------------------------
    # Ownership
    # --------------------------------------
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

    # Relationship links
    user = relationship("User", back_populates="credit_reservations")
    team = relationship("Team", back_populates="credit_reservations")

    # --------------------------------------
    # Reservation details
    # --------------------------------------
    amount: Mapped[float] = mapped_column(
        Numeric(18, 6),
        nullable=False
    )

    # Links to a bulk job or API transaction
    job_id: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
        index=True
    )

    locked: Mapped[bool] = mapped_column(Boolean, default=True)

    expires_at: Mapped[DateTime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True
    )

    reference: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True
    )

    __table_args__ = (
        Index("idx_reservation_user_job", "user_id", "job_id"),
    )

    def __repr__(self):
        return (
            f"<CreditReservation id={self.id} user={self.user_id} "
            f"amount={self.amount} locked={self.locked}>"
        )
