@router.post("/stripe/webhook")
async def stripe_webhook(request: Request):
    # ... existing verification code ...

    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        customer = session["customer"]
        price_id = session["subscription"]  # subscription object

        db = SessionLocal()
        try:
            user = db.query(User).filter(User.stripe_customer_id == customer).first()
            if not user:
                raise ValueError("user_not_found")

            # MAP price → plan
            if session["mode"] == "subscription":
                price = session["display_items"][0]["price"]["id"] \
                    if "display_items" in session else None

                plan_name = None
                if price == settings.STRIPE_PRICE_PRO:
                    plan_name = "pro"
                elif price == settings.STRIPE_PRICE_TEAM:
                    plan_name = "team"
                elif price == settings.STRIPE_PRICE_ENTERPRISE:
                    plan_name = "enterprise"

                if plan_name:
                    user.plan = plan_name
                    db.add(user)
                    db.commit()
        finally:
            db.close()

if event["type"] in (
    "customer.subscription.deleted",
    "customer.subscription.updated",
    "invoice.payment_failed"
):
    sub = event["data"]["object"]
    customer_id = sub["customer"]

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.stripe_customer_id == customer_id).first()
        if user:
            user.plan = "free"
            db.add(user)
            db.commit()
    finally:
        db.close()

# backend/app/api/v1/webhooks.py
import logging
import stripe
from fastapi import APIRouter, Request, Header, HTTPException
from backend.app.config import settings
from backend.app.services.stripe_handlers import handle_checkout_session, handle_invoice_paid, handle_invoice_payment_failed

router = APIRouter(prefix="/api/v1/webhooks", tags=["webhooks"])
logger = logging.getLogger(__name__)

# Raw body is required for Stripe signature verification
@router.post("/stripe")
async def stripe_webhook(request: Request, stripe_signature: str = Header(None)):
    payload = await request.body()
    if not settings.STRIPE_WEBHOOK_SECRET:
        logger.error("STRIPE_WEBHOOK_SECRET not configured")
        raise HTTPException(status_code=500, detail="webhook_not_configured")

    try:
        event = stripe.Webhook.construct_event(payload=payload, sig_header=stripe_signature, secret=settings.STRIPE_WEBHOOK_SECRET)
    except ValueError:
        # invalid payload
        logger.exception("Invalid stripe payload")
        raise HTTPException(status_code=400, detail="invalid_payload")
    except stripe.error.SignatureVerificationError:
        logger.exception("Invalid stripe signature")
        raise HTTPException(status_code=400, detail="invalid_signature")

    # Handle events
    evt_type = event["type"]
    obj = event["data"]["object"]

    try:
        if evt_type == "checkout.session.completed":
            handle_checkout_session(obj)
        elif evt_type in ("invoice.payment_succeeded", "invoice.paid"):
            handle_invoice_paid(obj)
        elif evt_type == "invoice.payment_failed":
            handle_invoice_payment_failed(obj)
        # add more events as needed
    except Exception:
        logger.exception("Failed to handle stripe event: %s", evt_type)
    return {"ok": True}


# inside backend/app/api/v1/webhooks.py (event dispatching part)
from backend.app.services.stripe_handlers import (
    handle_checkout_session,
    handle_invoice_paid,
    handle_invoice_payment_failed,
    handle_subscription_created,
    handle_subscription_updated,
    handle_subscription_deleted,
)

# After parsing `event` and `obj`:
evt_type = event["type"]
obj = event["data"]["object"]

try:
    if evt_type == "checkout.session.completed":
        handle_checkout_session(obj)
    elif evt_type in ("invoice.payment_succeeded", "invoice.paid"):
        handle_invoice_paid(obj)
    elif evt_type == "invoice.payment_failed":
        handle_invoice_payment_failed(obj)
    elif evt_type == "customer.subscription.created":
        handle_subscription_created(obj)
    elif evt_type == "customer.subscription.updated":
        handle_subscription_updated(obj)
    elif evt_type == "customer.subscription.deleted":
        handle_subscription_deleted(obj)
    # add other event types if you wish
except Exception:
    logger.exception("Failed to handle stripe event: %s", evt_type)
