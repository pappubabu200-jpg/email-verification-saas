# backend/app/services/billing_service.py

import logging
from decimal import Decimal

import stripe
from fastapi import HTTPException

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.config import settings
from backend.app.db import async_session
from backend.app.models.user import User
from backend.app.services.credits_service import add_credits

logger = logging.getLogger(__name__)

stripe.api_key = settings.STRIPE_SECRET_KEY


# ---------------------------------------------------------
# 1. CREATE CHECKOUT SESSION (INR)
# ---------------------------------------------------------

async def create_checkout_session(
    user_id: int,
    amount_in_inr: int,
    success_url: str,
    cancel_url: str
) -> dict:
    """
    Creates a Stripe Checkout session for INR-based credit top-ups.
    """

    if not stripe.api_key:
        raise HTTPException(status_code=500, detail="stripe_not_configured")

    # Convert rupees → paise
    amount_paise = int(amount_in_inr) * 100

    try:
        session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            mode="payment",
            customer=None,       # optional (if you want customer tracking)
            metadata={"user_id": str(user_id)},
            line_items=[{
                "price_data": {
                    "currency": "inr",
                    "product_data": {"name": "Credit Top-Up"},
                    "unit_amount": amount_paise,
                },
                "quantity": 1,
            }],
            success_url=success_url,
            cancel_url=cancel_url,
        )

        return {"id": session.id, "url": session.url}

    except Exception as e:
        logger.exception("Stripe checkout session error: %s", e)
        raise HTTPException(status_code=500, detail=f"stripe_error: {str(e)}")


# ---------------------------------------------------------
# 2. HANDLE STRIPE WEBHOOK EVENTS (CREDITS)
# ---------------------------------------------------------

async def handle_stripe_event(event: dict):
    """
    Handles:
        - payment_intent.succeeded
        - checkout.session.completed

    Adds credits to user.
    """

    typ = event.get("type")
    data = event.get("data", {}).get("object", {})

    # --------- Supported Events ----------
    if typ not in ("payment_intent.succeeded", "checkout.session.completed"):
        return False

    metadata = data.get("metadata") or {}
    user_id = metadata.get("user_id")

    # Amount paid in cents
    amount_cents = data.get("amount_total") or data.get("amount", 0)
    amount_inr = Decimal(amount_cents) / Decimal(100)

    if not user_id:
        logger.warning("Stripe webhook: missing user_id in metadata")
        return False

    # Credits mapping: 1 INR = 1 credit
    credits = amount_inr

    async with async_session() as db:
        # Verify user exists
        q = await db.execute(select(User).where(User.id == int(user_id)))
        user = q.scalar_one_or_none()

        if not user:
            logger.error("Stripe webhook: user not found: %s", user_id)
            return False

        # Add credits
        await add_credits(
            user_id=user.id,
            amount=credits,
            reference=f"stripe:{data.get('id')}",
            metadata=str(metadata),
        )

        return True


# ---------------------------------------------------------
# 3. CREATE ONE-TIME USD INVOICE ITEM (ADMIN)
# ---------------------------------------------------------

async def add_overage_invoice_item(customer_id: str, amount_usd: float, description: str):
    """
    Create a Stripe invoice item (used for admin-based overage billing).
    """

    try:
        stripe.InvoiceItem.create(
            customer=customer_id,
            amount=int(amount_usd * 100),
            currency="usd",
            description=description,
        )
        return True
    except Exception as e:
        logger.exception("Failed invoice item: %s", e)
        return False


# ---------------------------------------------------------
# 4. ADMIN TOP-UP (CREDITS)
# ---------------------------------------------------------

async def admin_topup_user(user_id: int, credits: Decimal, reference: str = None) -> bool:
    """
    Admin-controlled credits (used after manual adjustments).
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
