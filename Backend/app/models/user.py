from sqlalchemy import Column, Integer, String, Boolean, Numeric
from backend.app.db import Base
from backend.app.models.base import IdMixin, TimestampMixin

class User(Base, IdMixin, TimestampMixin):
    __tablename__ = "users"

    email = Column(String(255), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    is_active = Column(Boolean, default=True)
    is_admin = Column(Boolean, default=False)

    # NEW FIELDS
    plan = Column(String(100), nullable=True, index=True)  # free / pro / team / enterprise
    credits = Column(Numeric(18, 6), nullable=False, server_default="0")  # user credit balance

    stripe_customer_id = Column(String(255), nullable=True)
