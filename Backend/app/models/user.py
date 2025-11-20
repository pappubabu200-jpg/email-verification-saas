from sqlalchemy import Column, String, Boolean, Integer
from backend.app.db import Base
from backend.app.models.base import IdMixin, TimestampMixin

class User(Base, IdMixin, TimestampMixin):
    __tablename__ = "users"

    email = Column(String(255), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    is_admin = Column(Boolean, default=False, nullable=False)
    stripe_customer_id = Column(String(255), nullable=True)

    def __repr__(self) -> str:
        return f"<User id={self.id} email={self.email}>"
