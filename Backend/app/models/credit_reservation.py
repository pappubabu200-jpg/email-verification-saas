from sqlalchemy import Column, Integer, Numeric, String, Boolean, DateTime, ForeignKey
from backend.app.db import Base
from backend.app.models.base import IdMixin, TimestampMixin
from sqlalchemy.sql import func

class CreditReservation(Base, IdMixin, TimestampMixin):
    __tablename__ = "credit_reservations"

    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    amount = Column(Numeric(18,6), nullable=False)
    job_id = Column(String(128), nullable=True, index=True)
    locked = Column(Boolean, default=True, nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    reference = Column(String(255), nullable=True)

    def __repr__(self):
        return f"<CreditReservation id={self.id} user={self.user_id} amount={self.amount} locked={self.locked}>"
