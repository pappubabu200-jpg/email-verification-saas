from datetime import datetime
import hashlib
import secrets

from sqlalchemy import (
    Column,
    String,
    Boolean,
    Integer,
    ForeignKey,
    UniqueConstraint,
    Index,
)
from sqlalchemy.orm import relationship, Mapped, mapped_column

from backend.app.db import Base
from backend.app.models.base import IdMixin, TimestampMixin


class ApiKey(Base, IdMixin, TimestampMixin):
    """
    Represents a user's API key with rate limiting, daily limits,
    activation control, and secure hashed storage of API keys.

    NOTE:
        - Raw API keys are NEVER stored.
        - Only SHA-256 hashes are saved.
        - Use `ApiKey.generate_key()` to create + hash keys safely.
    """

    __tablename__ = "api_keys"

    # ------------------------------
    # Columns
    # ------------------------------

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )

    # Store only SHA256 hash — not the raw key
    key_hash: Mapped[str] = mapped_column(
        String(64),  # SHA-256 hex = 64 chars
        unique=True,
        index=True,
        nullable=False,
    )

    name: Mapped[str | None] = mapped_column(String(255), nullable=True)

    active: Mapped[bool] = mapped_column(Boolean, default=True)

    # Daily quota
    daily_limit: Mapped[int] = mapped_column(Integer, default=5000)
    used_today: Mapped[int] = mapped_column(Integer, default=0)

    # Per-key RPS limiter (0 = use global default)
    rate_limit_per_sec: Mapped[int] = mapped_column(Integer, default=0)

    # ------------------------------
    # Relationships
    # ------------------------------

    user = relationship("User", back_populates="api_keys")

    # ------------------------------
    # SQL constraints
    # ------------------------------

    __table_args__ = (
        UniqueConstraint("user_id", "name", name="uq_user_key_name"),
        Index("idx_api_key_user_active", "user_id", "active"),
    )

    # ------------------------------
    # Utility methods
    # ------------------------------

    @staticmethod
    def generate_raw_key(length: int = 48) -> str:
        """
        Generates a secure raw API key. 
        Do NOT store this raw key in the database.

        Example output: 74-character base64 string
        """
        return secrets.token_urlsafe(length)

    @staticmethod
    def hash_key(raw_key: str) -> str:
        """Hashes the API key using SHA-256."""
        return hashlib.sha256(raw_key.encode()).hexdigest()

    @classmethod
    def create_key(cls, user_id: int, name: str | None = None):
        """
        Generate a raw API key and a hashed version to store.

        Returns:
            (raw_key, ApiKey instance)
        """
        raw_key = cls.generate_raw_key()
        key_hash = cls.hash_key(raw_key)

        obj = cls(
            user_id=user_id,
            key_hash=key_hash,
            name=name,
        )

        return raw_key, obj

    def verify_key(self, raw_key: str) -> bool:
        """Verify if a raw API key matches the stored hash."""
        return self.key_hash == self.hash_key(raw_key)

    def __repr__(self):
        return (
            f"<ApiKey id={self.id} user_id={self.user_id} "
            f"active={self.active} daily_used={self.used_today}/{self.daily_limit}>"
        )
