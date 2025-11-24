# backend/app/api/v1/subscription_events.py
from fastapi import APIRouter, Request, HTTPException
import logging
from backend.app.db import SessionLocal

router = APIRouter(prefix="/api/v1/subscription-events", tags=["subscriptions"])
logger = logging.getLogger(__name__)

# lightweight webhook receiver for subscription events (Stripe, Razorpay, etc.)
@router.post("/webhook")
async def subscription_webhook(request: Request):
    """
    Generic webhook proxy for subscription events.
    - Accepts raw JSON from payment provider
    - Logs event and saves to DB (if webhook model exists)
    - Returns 200 on success.
    """
    payload = await request.body()
    try:
        data = await request.json()
    except Exception:
        data = {"raw": payload.decode("utf-8", errors="ignore")}

    logger.info("subscription webhook received: %s", (data if isinstance(data, dict) else str(data)[:200]))

    # try to persist event into DB table webhook_endpoint or subscriptions_db
    try:
        db = SessionLocal()
        # attempt to save to a generic `webhook_events` table if exists
        WebhookEvent = None
        try:
            WebhookEvent = __import__("backend.app.models.webhook_event", fromlist=["WebhookEvent"]).WebhookEvent
        except Exception:
            # fallback: try subscriptions_db model if present
            try:
                WebhookEvent = __import__("backend.app.models.webhook_endpoint", fromlist=["WebhookEndpoint"]).WebhookEndpoint
            except Exception:
                WebhookEvent = None

        if WebhookEvent:
            ev = WebhookEvent(payload=str(data))
            db.add(ev)
            db.commit()
        db.close()
    except Exception:
        logger.exception("webhook persist failed (non-fatal)")

    return {"ok": True}
