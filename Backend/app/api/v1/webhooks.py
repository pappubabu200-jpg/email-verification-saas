import logging
import stripe
from fastapi import APIRouter, Request, Header, HTTPException
from backend.app.config import settings
from backend.app.services.stripe_handlers import (
    handle_checkout_session,
    handle_invoice_paid,
    handle_invoice_payment_failed,
    handle_subscription_created,
    handle_subscription_updated,
    handle_subscription_deleted,
)

router = APIRouter(prefix="/api/v1/webhooks", tags=["webhooks"])
logger = logging.getLogger(__name__)

@router.post("/stripe")
async def stripe_webhook(request: Request, stripe_signature: str = Header(...)):
    payload = await request.body()

    if not settings.STRIPE_WEBHOOK_SECRET:
        logger.error("STRIPE_WEBHOOK_SECRET not configured")
        raise HTTPException(status_code=500, detail="webhook_not_configured")

    try:
        event = stripe.Webhook.construct_event(
            payload=payload,
            sig_header=stripe_signature,
            secret=settings.STRIPE_WEBHOOK_SECRET
        )
    except ValueError:
        logger.exception("Invalid stripe payload")
        raise HTTPException(status_code=400, detail="invalid_payload")
    except stripe.error.SignatureVerificationError:
        logger.exception("Invalid stripe signature")
        raise HTTPException(status_code=400, detail="invalid_signature")

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
        else:
            logger.info(f"Unhandled Stripe event type: {evt_type}")
    except Exception as e:
        logger.exception(f"Failed to handle stripe event {evt_type}: {e}")
        # Consider returning 500 or appropriate HTTP status if failures are critical

    return {"ok": True}
