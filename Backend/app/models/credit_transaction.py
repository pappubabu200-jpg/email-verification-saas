from sqlalchemy import Column, Integer, Numeric, String, Text, ForeignKey
from backend.app.db import Base
from backend.app.models.base import IdMixin, TimestampMixin

# A record of credit topups and charges (amount positive = topup, negative = charge)
class CreditTransaction(Base, IdMixin, TimestampMixin):
    __tablename__ = "credit_transactions"

    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    amount = Column(Numeric(18, 6), nullable=False)  # allow fractional credits if needed
    balance_after = Column(Numeric(18, 6), nullable=False)
    type = Column(String(50), nullable=False)  # e.g., "topup", "charge", "refund"
    reference = Column(String(255), nullable=True)
    metadata = Column(Text, nullable=True)

    def __repr__(self):
        return f"<CreditTransaction id={self.id} user={self.user_id} amount={self.amount} balance_after={self.balance_after}>"
