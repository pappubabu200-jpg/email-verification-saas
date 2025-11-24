from sqlalchemy import (
    String,
    Boolean,
    Integer,
    DateTime,
    Index
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func
from backend.app.db import Base
from backend.app.models.base import IdMixin


class DomainCache(Base, IdMixin):
    """
    Caches domain-level verification results to improve performance.
    """

    __tablename__ = "domain_cache"

    domain: Mapped[str] = mapped_column(String(255), unique=True, index=True)

    has_dns: Mapped[bool] = mapped_column(Boolean, default=False)
    mx_found: Mapped[bool] = mapped_column(Boolean, default=False)
    is_disposable: Mapped[bool] = mapped_column(Boolean, default=False)
    is_catch_all: Mapped[bool] = mapped_column(Boolean, default=False)

    provider: Mapped[str | None] = mapped_column(String(100), nullable=True)

    refreshed_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        index=True
    )

    __table_args__ = (
        Index("idx_domain_cache_flags", "is_disposable", "is_catch_all"),
    )

    def __repr__(self):
        return f"<DomainCache domain={self.domain}>"
