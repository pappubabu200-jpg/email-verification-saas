from sqlalchemy import Column, Integer, String, Numeric, ForeignKey
from backend.app.db import Base
from backend.app.models.base import IdMixin, TimestampMixin

class Team(Base, IdMixin, TimestampMixin):
    __tablename__ = "teams"

    name = Column(String(255), nullable=False)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    credits = Column(Numeric(18, 6), nullable=False, server_default="0")
