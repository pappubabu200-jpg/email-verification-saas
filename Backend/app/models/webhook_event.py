# backend/app/models/webhook_event.py
from __future__ import annotations

import hashlib
import hmac
import json
import time
from datetime import datetime, timedelta, UTC
from typing import Dict, Optional

from sqlalchemy import (
    Integer, String, Text, Boolean, DateTime,
    ForeignKey, Index, UniqueConstraint, func
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.db import Base
from backend.app.models.base import IdMixin, TimestampMixin


class WebhookEvent(Base, IdMixin, TimestampMixin):
    """
    Complete webhook system with:
    - Signature verification (Stripe, Shopify, Paddle, etc.)
    - Idempotency
    - Exponential backoff retries
    - Rate limiting (per endpoint, per IP, per provider)
    - Dead-letter queue
    """

    __tablename__ = "webhook_events"

    # ------------------------------------------------------------------
    # Core
    # ------------------------------------------------------------------
    endpoint_id: Mapped[int] = mapped_column(
        ForeignKey("webhook_endpoints.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    endpoint = relationship("WebhookEndpoint", back_populates="events_sent")

    provider: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    event_type: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    payload: Mapped[str] = mapped_column(Text, nullable=False)

    # Source IP (for rate limiting & abuse detection)
    source_ip: Mapped[str | None] = mapped_column(String(45), nullable=True, index=True)  # IPv4 + IPv6

    # ------------------------------------------------------------------
    # Idempotency & Security
    # ------------------------------------------------------------------
    external_event_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    signature_verified: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    signature_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ------------------------------------------------------------------
    # Delivery State
    # ------------------------------------------------------------------
    delivered: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    response_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    response_body: Mapped[str | None] = mapped_column(Text, nullable=True)
    delivered_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    failed_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    next_retry_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    dead: Mapped[bool] = mapped_column(Boolean, default=False, index=True)

    # ------------------------------------------------------------------
    # Constraints
    # ------------------------------------------------------------------
    __table_args__ = (
        UniqueConstraint("external_event_id", name="uq_webhook_external_event_id"),
        Index("idx_webhook_retry_queue", "next_retry_at"),
        Index("idx_webhook_rate_limit", "endpoint_id", "source_ip", "created_at"),
        Index("idx_webhook_provider_rate", "provider", "created_at"),
    )

    # ==================================================================
    # RATE LIMITING LOGIC (3 layers)
    # ==================================================================
    @staticmethod
    def is_rate_limited(
        db,
        endpoint_id: int,
        source_ip: str | None,
        provider: str | None = None,
        window_minutes: int = 1,
        max_per_window: int = 100
    ) -> tuple[bool, int, str]:
        """
        Returns (is_limited: bool, remaining: int, reset_in_seconds: int)
        Three-tier protection:
          1. Per endpoint + IP   → 100 req/min (default)
          2. Per endpoint        → 500 req/min
          3. Global per provider → 1000 req/min (e.g. Stripe flood)
        """
        now = datetime.now(UTC)
        window_start = now - timedelta(minutes=window_minutes)

        # 1. Per endpoint + IP (most granular)
        if source_ip:
            count_ip = db.query(WebhookEvent).filter(
                WebhookEvent.endpoint_id == endpoint_id,
                WebhookEvent.source_ip == source_ip,
                WebhookEvent.created_at >= window_start
            ).count()

            if count_ip >= max_per_window:
                return True, 0, int((window_start + timedelta(minutes=window_minutes+1) - now).total_seconds())

        # 2. Per endpoint (no IP)
        count_endpoint = db.query(func.count()).filter(
            WebhookEvent.endpoint_id == endpoint_id,
            WebhookEvent.created_at >= window_start
        ).scalar() or 0

        if count_endpoint >= max_per_window * 5:  # 500/min
            return True, 0, 60

        # 3. Per provider (flood protection)
        if provider:
            count_provider = db.query(func.count()).filter(
                WebhookEvent.provider == provider,
                WebhookEvent.created_at >= window_start
            ).scalar() or 0

            if count_provider >= 1000:  # Stripe sends max ~200/min normally
                return True, 0, 60

        remaining = max_per_window - (count_ip if source_ip else count_endpoint)
        return False, max(0, remaining), 0

    # ==================================================================
    # SIGNATURE VERIFICATION (unchanged from previous version)
    # ==================================================================
    def verify_signature(self, headers: Dict[str, str]) -> bool:
        secret = self.endpoint.secret
        raw_body = self.payload.encode("utf-8")

        try:
            if self.provider == "stripe":
                return self._verify_stripe(headers, raw_body, secret)
            elif self.provider == "shopify":
                return self._verify_shopify(headers, raw_body, secret)
            elif self.provider == "paddle":
                return self._verify_paddle(headers, raw_body, secret)
            elif self.provider == "lemonsqueezy":
                return self._verify_lemonsqueezy(headers, raw_body, secret)
            elif self.provider == "github":
                return self._verify_github(headers, raw_body, secret)
            else:
                self.signature_verified = True
                return True
        except Exception as e:
            self.signature_verified = False
            self.signature_error = str(e)
            return False

    # ... (keep all _verify_* methods from previous answer) ...

    # ==================================================================
    # RETRY LOGIC (unchanged)
    # ==================================================================
    def mark_as_failed(self, status: int, body: str = "") -> None:
        self.response_status = status
        self.response_body = (body or "")[:10_000]
        self.failed_at = datetime.now(UTC)
        self.retry_count += 1

        if self.retry_count >= 10:
            self.dead = True
            self.next_retry_at = None
            return

        delay = min(5 * (2 ** (self.retry_count - 1)), 1440)
        self.next_retry_at = datetime.now(UTC) + timedelta(minutes=delay)

    def mark_as_delivered(self, status: int = 200) -> None:
        self.delivered = True
        self.delivered_at = datetime.now(UTC)
        self.response_status = status
        self.next_retry_at = None

    def should_retry_now(self) -> bool:
        if not self.signature_verified or self.delivered or self.dead:
            return False
        return self.next_retry_at is None or datetime.now(UTC) >= self.next_retry_at

    def __repr__(self) -> str:
        return f"<WebhookEvent {self.id} {self.provider}/{self.event_type} ip={self.source_ip} sig={self.signature_verified}>"
