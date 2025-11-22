from sqlalchemy import Column, Integer, Numeric, ForeignKey
from backend.app.db import Base
from backend.app.models.base import IdMixin, TimestampMixin

class TeamBalance(Base, IdMixin, TimestampMixin):
    __tablename__ = "team_balances"

    team_id = Column(Integer, ForeignKey("teams.id"), nullable=False, unique=True, index=True)
    balance = Column(Numeric(18,6), nullable=False, default=0)
