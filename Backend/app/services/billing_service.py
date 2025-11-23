from decimal import Decimal
from typing import Optional
import os
import stripe
from fastapi import HTTPException

from backend.app.config import settings
from backend.app.db import SessionLocal
from backend.app.services.credits_service import add_credits

# initialize stripe if key present
STRIPE_KEY = os.getenv("STRIPE_SECRET_KEY") or settings.STRIPE_SECRET_KEY
if STRIPE_KEY:
    stripe.api_key = STRIPE_KEY


def create_stripe_checkout_session(amount_in_inr: int, currency: str = "inr", success_url: str = "/", cancel_url: str = "/") -> dict:
    """
    Create a simple Stripe checkout session for topup.
    amount_in_inr: integer rupees (e.g. 100 for ₹100) — convert to paise for Stripe.
    """
    if not STRIPE_KEY:
        raise HTTPException(status_code=500, detail="stripe_not_configured")

    try:
        session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            line_items=[{
                "price_data": {
                    "currency": currency,
                    "product_data": {"name": "Credit Topup"},
                    "unit_amount": int(amount_in_inr * 100),
                    "recurring": None
                },
                "quantity": 1
            }],
            mode="payment",
            success_url=success_url,
            cancel_url=cancel_url,
        )
        return {"id": session.id, "url": session.url}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"stripe_error: {str(e)}")


def handle_stripe_payment_intent(event: dict):
    """
    Minimal handler for stripe events. You must verify signature in webhook route.
    This expects the event contains metadata: {user_id, credits}
    """
    typ = event.get("type")
    data = event.get("data", {}).get("object", {})
    # For simplicity, handle payment_intent.succeeded and checkout.session.completed
    if typ in ("payment_intent.succeeded", "checkout.session.completed"):
        # check metadata or assume amount->credits mapping
        metadata = data.get("metadata", {}) or {}
        user_id = metadata.get("user_id")
        credits = metadata.get("credits")
        amount = data.get("amount_total") or data.get("amount")  # in cents
        # Convert credits or estimate: if credits provided, use it; otherwise fallback
        if user_id and credits:
            try:
                credits_decimal = Decimal(str(credits))
            except Exception:
                credits_decimal = Decimal("0")
        else:
            # fallback: 1 credit per 1 INR (example). Convert amount (cents) to rupees
            if amount:
                rupees = Decimal(amount) / Decimal(100)
                credits_decimal = rupees  # 1 INR = 1 credit mapping — change as you like
            else:
                credits_decimal = Decimal("0")

        if user_id and credits_decimal > 0:
            # add credits to user
            db = SessionLocal()
            try:
                # create transaction
                add_credits(db, int(user_id), credits_decimal, type_="topup", reference=str(data.get("id")), metadata=str(metadata))
            finally:
                db.close()
            return True
    return False


import stripe
from backend.app.config import settings
stripe.api_key = settings.STRIPE_SECRET_KEY

def add_overage_invoice_item(customer_id: str, amount_usd: float, description: str):
    """
    Creates a one-time invoice item.
    Stripe will charge automatically.
    """
    stripe.InvoiceItem.create(
        customer=customer_id,
        amount=int(amount_usd * 100),  # cents
        currency="usd",
        description=description
        )


