# backend/app/services/stripe_handlers.py
import stripe
import logging
import json
from backend.app.config import settings
from backend.app.db import SessionLocal
from backend.app.models.user import User
from backend.app.services.credits_service import add_credits
from backend.app.services.webhook_dispatcher import send_webhook_async

logger = logging.getLogger(__name__)

stripe.api_key = settings.STRIPE_SECRET_KEY

def _find_user_by_customer(customer_id: str):
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.stripe_customer_id == customer_id).first()
        return user
    finally:
        db.close()

def handle_checkout_session(session):
    """
    Called when checkout.session.completed (one-time checkout or subscription).
    Expectation: session.metadata may contain user_id and/or topup_credits.
    """
    logger.info("Stripe checkout.session.completed received: %s", session.get("id"))
    metadata = session.get("metadata") or {}
    customer = session.get("customer") or session.get("customer_id")
    user = None
    if metadata.get("user_id"):
        try:
            uid = int(metadata.get("user_id"))
            db = SessionLocal()
            try:
                user = db.query(User).get(uid)
            finally:
                db.close()
        except Exception:
            user = None
    if not user and customer:
        user = _find_user_by_customer(customer)

    topup_credits = None
    if metadata.get("topup_credits"):
        try:
            topup_credits = int(metadata.get("topup_credits"))
        except Exception:
            topup_credits = None

    amount_total = session.get("amount_total") or session.get("amount_subtotal") or 0

    # If this was a one-time payment intended to top up credits:
    if user and (topup_credits or amount_total > 0):
        # Heuristic: try metadata topup_credits first, else use settings DEFAULT_TOPUP_CREDITS if present
        credits_to_add = topup_credits or getattr(settings, "DEFAULT_TOPUP_CREDITS", None) or 0
        if credits_to_add and credits_to_add > 0:
            try:
                add_credits(user.id, credits_to_add, reference=f"stripe:checkout:{session.get('id')}")
            except Exception:
                logger.exception("Failed to add credits after checkout for user %s", user.id)

    # Fire app-level webhook for other services (non-blocking)
    if session.get("metadata", {}).get("webhook_on_complete"):
        try:
            url = session.get("metadata").get("webhook_on_complete")
            payload = {"event": "billing.checkout_completed", "stripe_session": session}
            send_webhook_async.delay(url, payload)
        except Exception:
            logger.exception("send webhook_on_complete failed")

def handle_invoice_paid(invoice):
    """
    Called on invoice.payment_succeeded / invoice.paid for subscriptions.
    Update subscription status and option to add credits if invoice contains metadata.
    """
    logger.info("Stripe invoice.paid %s", invoice.get("id"))
    customer = invoice.get("customer")
    metadata = invoice.get("metadata") or {}
    user = _find_user_by_customer(customer) if customer else None

    # If invoice metadata includes topup_credits -> credit the user
    if user and metadata.get("topup_credits"):
        try:
            credits = int(metadata.get("topup_credits"))
            add_credits(user.id, credits, reference=f"stripe:invoice:{invoice.get('id')}")
        except Exception:
            logger.exception("Failed to topup credits for invoice %s", invoice.get("id"))

def handle_invoice_payment_failed(invoice):
    """
    Called on invoice.payment_failed.
    Can be used to mark user subscription as past_due and notify admin / user.
    """
    logger.warning("Stripe invoice.payment_failed %s", invoice.get("id"))
    # Optionally, send webhook / email to user if user found.
    customer = invoice.get("customer")
    user = _find_user_by_customer(customer) if customer else None
    if user:
        # notify via webhook if user has webhook endpoint (not required)
        try:
            if hasattr(user, "webhook_url") and user.webhook_url:
                send_webhook_async.delay(user.webhook_url, {"event": "billing.invoice_failed", "invoice_id": invoice.get("id")})
        except Exception:
            logger.exception("notify invoice_failed failed")
