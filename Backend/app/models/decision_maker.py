from sqlalchemy import (
    Integer,
    String,
    Text,
    Boolean,
    ForeignKey,
    Index
)
from sqlalchemy.orm import relationship, Mapped, mapped_column

from backend.app.db import Base
from backend.app.models.base import IdMixin, TimestampMixin


class DecisionMaker(Base, IdMixin, TimestampMixin):
    """
    Stores scraped or enriched decision-maker contact information
    from sources like Apollo, PDL, Clearbit, Grok, etc.
    """

    __tablename__ = "decision_makers"

    # --------------------------------------
    # Ownership
    # --------------------------------------
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True
    )

    user = relationship("User", back_populates="decision_makers")

    # --------------------------------------
    # Company & Domain
    # --------------------------------------
    company: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        index=True
    )

    domain: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        index=True
    )

    # --------------------------------------
    # Personal Details
    # --------------------------------------
    first_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    last_name: Mapped[str | None] = mapped_column(String(128), nullable=True)

    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    role: Mapped[str | None] = mapped_column(String(255), nullable=True)

    email: Mapped[str | None] = mapped_column(
        String(320),
        nullable=True,
        index=True
    )

    # Source → e.g. "pdl", "apollo", "pattern", "grok", "custom_upload"
    source: Mapped[str | None] = mapped_column(String(100), nullable=True)

    raw: Mapped[str | None] = mapped_column(Text, nullable=True)
    verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    __table_args__ = (
        Index("idx_decision_maker_email_company", "email", "company"),
        Index("idx_decision_maker_domain_verified", "domain", "verified"),
    )

    # --------------------------------------
    # Helper methods
    # --------------------------------------
    def full_name(self) -> str:
        parts = [self.first_name, self.last_name]
        return " ".join([p for p in parts if p])

    def __repr__(self):
        return (
            f"<DecisionMaker id={self.id} email='{self.email}' "
            f"company='{self.company}' verified={self.verified}>"
    )
