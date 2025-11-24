from sqlalchemy import (
    String,
    Integer,
    Boolean,
    ForeignKey,
    Numeric,
    Index,
    Text,
    DateTime,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from backend.app.db import Base
from backend.app.models.base import IdMixin, TimestampMixin


class VerificationResult(Base, IdMixin, TimestampMixin):
    """
    Stores the result of a single email verification.
    Works for:
    - real-time API verifications
    - bulk CSV jobs
    - team / user billing
    """

    __tablename__ = "verification_results"

    # --------------------------------------
    # Ownership
    # --------------------------------------
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    team_id: Mapped[int | None] = mapped_column(
        ForeignKey("teams.id", ondelete="SET NULL"),
        nullable=True,
        index=True
    )

    bulk_job_id: Mapped[int | None] = mapped_column(
        ForeignKey("bulk_jobs.id", ondelete="SET NULL"),
        nullable=True,
        index=True
    )

    user = relationship("User")
    team = relationship("Team")
    bulk_job = relationship("BulkJob")

    # --------------------------------------
    # Email Data
    # --------------------------------------
    email: Mapped[str] = mapped_column(
        String(320),
        index=True,
        nullable=False
    )

    domain: Mapped[str | None] = mapped_column(
        String(255),
        index=True,
        nullable=True
    )

    # --------------------------------------
    # Verification Status
    # --------------------------------------
    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False
    )
    """
    Examples:
        valid
        invalid
        disposable
        spamtrap
        catch_all
        unknown
        syntax_error
        domain_error
    """

    sub_status: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True
    )
    """
    Examples:
        smtp_accept_all
        mailbox_full
        role_account
        temporary_error
    """

    # --------------------------------------
    # Technical Checks
    # --------------------------------------
    is_disposable: Mapped[bool] = mapped_column(Boolean, default=False)
    is_role_account: Mapped[bool] = mapped_column(Boolean, default=False)
    is_catch_all: Mapped[bool] = mapped_column(Boolean, default=False)
    smtp_success: Mapped[bool] = mapped_column(Boolean, default=False)

    mx_records_found: Mapped[bool] = mapped_column(Boolean, default=False)
    has_dns: Mapped[bool] = mapped_column(Boolean, default=False)

    # Raw diagnostic logs (optional)
    diagnostics: Mapped[str | None] = mapped_column(
        Text,
        nullable=True
    )

    # --------------------------------------
    # Billing (optional but recommended)
    # --------------------------------------
    cost: Mapped[float | None] = mapped_column(
        Numeric(10, 4),
        nullable=True
    )

    verified_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        index=True
    )

    __table_args__ = (
        Index("idx_verify_user_email", "user_id", "email"),
        Index("idx_verify_domain_status", "domain", "status"),
    )

    def __repr__(self):
        return f"<VerificationResult email={self.email} status={self.status}>"
