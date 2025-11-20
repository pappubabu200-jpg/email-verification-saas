from sqlalchemy import Column, Integer, String, Text, ForeignKey, Boolean
from backend.app.db import Base
from backend.app.models.base import IdMixin, TimestampMixin

class DecisionMaker(Base, IdMixin, TimestampMixin):
    __tablename__ = "decision_makers"

    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    company = Column(String(255), nullable=True, index=True)
    domain = Column(String(255), nullable=True, index=True)
    first_name = Column(String(128), nullable=True)
    last_name = Column(String(128), nullable=True)
    title = Column(String(255), nullable=True)
    role = Column(String(255), nullable=True)
    email = Column(String(320), nullable=True, index=True)
    source = Column(String(100), nullable=True)  # e.g. "pdl", "apollo", "pattern", "grok"
    raw = Column(Text, nullable=True)
    verified = Column(Boolean, default=False, nullable=False)

    def full_name(self):
        return " ".join(filter(None, [self.first_name, self.last_name]))
