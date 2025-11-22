from sqlalchemy import Column, Integer, Numeric, String, Text, ForeignKey
from backend.app.db import Base
from backend.app.models.base import IdMixin, TimestampMixin

class TeamCreditTransaction(Base, IdMixin, TimestampMixin):
    __tablename__ = "team_credit_transactions"

    team_id = Column(Integer, ForeignKey("teams.id"), nullable=False, index=True)
    amount = Column(Numeric(18,6), nullable=False)
    balance_after = Column(Numeric(18,6), nullable=False)
    type = Column(String(50), nullable=False)  # topup, debit, refund, transfer_out, transfer_in
    reference = Column(String(255), nullable=True)
    metadata = Column(Text, nullable=True)
