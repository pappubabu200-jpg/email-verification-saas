# backend/app/services/billing_service.py

import logging
from decimal import Decimal
from typing import Optional

import stripe
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.config import settings
from backend.app.db import async_session
from backend.app.models.user import User
from backend.app.services.credits_service import add_credits

logger = logging.getLogger(__name__)

# Stripe Initialization
stripe.api_key = settings.STRIPE_SECRET_KEY


# ---------------------------------------------------------
# 1. CREATE CHECKOUT SESSION (INR TOPUP)
# ---------------------------------------------------------

async def create_checkout_session(
    user_id: int,
    amount_in_inr: int,
    success_url: str,
    cancel_url: str
) -> dict:
    """
    Creates a Stripe Checkout session for credit top-ups (INR → paise).
    """
    if not stripe.api_key:
        raise HTTPException(status_code=500, detail="stripe_not_configured")

    try:
        session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            mode="payment",
            customer=None,      # you can attach actual customer if needed
            metadata={"user_id": str(user_id)},
            line_items=[{
                "price_data": {
                    "currency": "inr",
                    "product_data": {"name": "Credit Top-Up"},
                    "unit_amount": amount_in_inr * 100,  # ₹ → paise
                },
                "quantity": 1,
            }],
            success_url=success_url,
            cancel_url=cancel_url,
        )
        return {"id": session.id, "url": session.url}

    except Exception as e:
        logger.exception("Stripe checkout error: %s", e)
        raise HTTPException(status_code=500, detail=f"stripe_error: {str(e)}")


# ---------------------------------------------------------
# 2. STRIPE WEBHOOK HANDLER
# ---------------------------------------------------------

async def handle_stripe_event(event: dict) -> bool:
    """
    Handles:
      - checkout.session.completed
      - payment_intent.succeeded

    Adds credits to user based on amount paid.
    """

    event_type = event.get("type")
    data = event.get("data", {}).get("object", {})

    if event_type not in ("checkout.session.completed", "payment_intent.succeeded"):
        return False

    # Extract metadata (user_id must be there)
    metadata = data.get("metadata") or {}
    user_id = metadata.get("user_id")

    if not user_id:
        logger.warning("Webhook missing user_id metadata")
        return False

    # Normalize amount (Stripe uses cents)
    cents = data.get("amount_total") or data.get("amount") or 0
    amount_inr = Decimal(str(cents)) / Decimal(100)

    credits = amount_inr  # 1 INR → 1 credit mapping

    async with async_session() as db:
        stmt = select(User).where(User.id == int(user_id))
        q = await db.execute(stmt)
        user = q.scalar_one_or_none()

        if not user:
            logger.error("Webhook user not found: %s", user_id)
            return False

        try:
            await add_credits(
                user_id=user.id,
                amount=credits,
                reference=f"stripe:{data.get('id')}",
                metadata=str(metadata),
            )
            return True

        except Exception as e:
            logger.exception("Credit add error: %s", e)
            return False


# ---------------------------------------------------------
# 3. ADMIN — CREATE INVOICE ITEM (USD)
# ---------------------------------------------------------

async def add_overage_invoice_item(
    customer_id: str,
    amount_usd: float,
    description: str
) -> bool:
    """
    Admin-only helper for Stripe billing adjustments.
    Creates one-time invoice item.
    """
    try:
        stripe.InvoiceItem.create(
            customer=customer_id,
            amount=int(amount_usd * 100),  # USD → cents
            currency="usd",
            description=description,
        )
        return True

    except Exception as e:
        logger.exception("Invoice item error: %s", e)
        return False


# ---------------------------------------------------------
# 4. ADMIN TOPUP CREDITS
# ---------------------------------------------------------

async def admin_topup_user(
    user_id: int,
    credits: Decimal,
    reference: Optional[str] = None
) -> bool:
    """
    Admin-controlled credits (manual adjustments).
    """

    async with async_session() as db:
        q = await db.execute(select(User).where(User.id == user_id))
        user = q.scalar_one_or_none()

        if not user:
            return False

        try:
            await add_credits(
                user_id=user.id,
                amount=credits,
                reference=reference or "admin_topup",
            )
            return True

        except Exception as e:
            logger.exception("Admin topup failed: %s", e)
            return False
