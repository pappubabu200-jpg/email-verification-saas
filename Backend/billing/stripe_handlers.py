# backend/app/billing/stripe_handlers.py
import os
import stripe
import logging
from decimal import Decimal
from fastapi import APIRouter, Request, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from backend.app.db import SessionLocal
from backend.app.models.user import User
from backend.app.services.credits_service import add_credits
from backend.app.services.plan_service import get_plan_by_name
from backend.app.services.pricing_service import get_cost_for_key

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/billing/stripe", tags=["stripe-billing"])

# Configure stripe from env
STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY", "")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "")
STRIPE_PRICE_ID_SUBSCRIPTION_PRO = os.getenv("STRIPE_PRICE_ID_SUBSCRIPTION_PRO", "")  # optional
STRIPE_SUCCESS_URL = os.getenv("STRIPE_SUCCESS_URL", "https://yourfrontend.example/success")
STRIPE_CANCEL_URL = os.getenv("STRIPE_CANCEL_URL", "https://yourfrontend.example/cancel")

stripe.api_key = STRIPE_SECRET_KEY

# --------------------------
# Helper utilities
# --------------------------
def get_user(db, user_id: int):
    return db.query(User).get(user_id)

def ensure_stripe_customer(db, user: User):
    """
    Create Stripe Customer if not exists and save stripe_customer_id on User.
    """
    if getattr(user, "stripe_customer_id", None):
        return user.stripe_customer_id

    cust = stripe.Customer.create(
        email=user.email,
        metadata={"user_id": str(user.id)}
    )
    user.stripe_customer_id = cust["id"]
    db.add(user)
    db.commit()
    return cust["id"]

# --------------------------
# Create Checkout Session (Subscription) - Frontend will redirect user to this URL
# --------------------------
@router.post("/create-subscription-session")
async def create_subscription_session(request: Request, current_user = Depends(lambda: getattr(request.state, "user", None))):
    """
    Create a Stripe Checkout Session for subscription (Pro/Team etc).
    Frontend should POST /api/v1/billing/stripe/create-subscription-session with chosen `price_id`.
    Returns session.id and session.url
    """
    payload = await request.json()
    price_id = payload.get("price_id") or STRIPE_PRICE_ID_SUBSCRIPTION_PRO
    if not price_id:
        raise HTTPException(status_code=400, detail="price_id_required")

    db = SessionLocal()
    try:
        user = get_user(db, getattr(current_user, "id", None))
        if not user:
            raise HTTPException(status_code=401, detail="auth_required")

        customer_id = ensure_stripe_customer(db, user)

        session = stripe.checkout.Session.create(
            customer=customer_id,
            mode="subscription",
            line_items=[{"price": price_id, "quantity": 1}],
            success_url=STRIPE_SUCCESS_URL + "?session_id={CHECKOUT_SESSION_ID}",
            cancel_url=STRIPE_CANCEL_URL,
            metadata={"user_id": str(user.id)},
        )
        return {"id": session.id, "url": session.url}
    finally:
        db.close()

# --------------------------
# One-time top-up (PaymentIntent)
# --------------------------
@router.post("/create-topup-intent")
async def create_topup_intent(request: Request, current_user = Depends(lambda: getattr(request.state, "user", None))):
    """
    Creates a one-time PaymentIntent for credits top-up.
    Body: {"amount_usd": 10.0, "currency": "usd"}
    We treat amount_usd as dollars; convert to cents.
    """
    data = await request.json()
    amount_usd = data.get("amount_usd")
    currency = data.get("currency", "usd").lower()
    if not amount_usd:
        raise HTTPException(400, "amount_usd required")

    cents = int(Decimal(str(amount_usd)) * 100)
    db = SessionLocal()
    try:
        user = get_user(db, getattr(current_user, "id", None))
        if not user:
            raise HTTPException(status_code=401, detail="auth_required")
        customer_id = ensure_stripe_customer(db, user)

        intent = stripe.PaymentIntent.create(
            amount=cents,
            currency=currency,
            customer=customer_id,
            metadata={"user_id": str(user.id), "purpose": "topup"},
        )
        return {"client_secret": intent.client_secret, "id": intent.id}
    finally:
        db.close()

# --------------------------
# Webhook endpoint — secure
# --------------------------
@router.post("/webhook")
async def stripe_webhook(request: Request):
    """
    Stripe webhook receiver. Configure your Stripe webhook to point here.
    This endpoint verifies the stripe signature header using STRIPE_WEBHOOK_SECRET.
    On relevant events we add credits or set subscriptions in DB as needed.
    """
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")

    # verify signature if secret is configured
    if STRIPE_WEBHOOK_SECRET:
        try:
            event = stripe.Webhook.construct_event(payload=payload, sig_header=sig_header, secret=STRIPE_WEBHOOK_SECRET)
        except ValueError as e:
            logger.exception("Invalid payload")
            raise HTTPException(status_code=400, detail="invalid_payload")
        except stripe.error.SignatureVerificationError as e:
            logger.exception("Invalid signature")
            raise HTTPException(status_code=400, detail="invalid_signature")
    else:
        # No webhook secret: parse unsafely (useful in dev only)
        try:
            event = stripe.Event.construct_from(await request.json(), stripe.api_key)
        except Exception:
            raise HTTPException(status_code=400, detail="invalid_event")

    # Handle events
    typ = event["type"]
    data = event["data"]["object"]

    # common helpers
    def _get_user_id_from_metadata(obj):
        try:
            mid = obj.get("metadata", {}).get("user_id")
            if mid:
                return int(mid)
        except Exception:
            pass
        # fallback: fetch from customer metadata
        try:
            cust = obj.get("customer")
            if cust:
                c = stripe.Customer.retrieve(cust)
                return int(c.get("metadata", {}).get("user_id"))
        except Exception:
            pass
        return None

    # Payment succeeded -> top-up or subscription payment
    try:
        if typ in ("payment_intent.succeeded", "checkout.session.completed", "invoice.paid"):
            # unify: find metadata user_id
            user_id = _get_user_id_from_metadata(data)
            if not user_id:
                logger.warning("stripe webhook: user_id not found in metadata for event %s", typ)
            else:
                db = SessionLocal()
                try:
                    # map to credit top-up: for PaymentIntent, use amount
                    if typ == "payment_intent.succeeded":
                        amt_cents = int(data.get("amount", 0))
                        amt_usd = Decimal(amt_cents) / 100
                        # determine credits mapping: 1 USD -> 1 credit (customize)
                        credits = float((amt_usd * Decimal("1")).quantize(Decimal("0.000001")))
                        add_credits(user_id, Decimal(str(credits)), reference=f"stripe:payment_intent:{data.get('id')}")
                        logger.info("credited user %s with %s credits (topup)", user_id, credits)
                    elif typ == "invoice.paid":
                        # For subscriptions you may want to assign plan access not credits.
                        # But if you sell credits via checkout, invoice.lines contains amount
                        amt_cents = int(data.get("amount_paid", 0) or data.get("total", 0) or 0)
                        amt_usd = Decimal(amt_cents) / 100
                        credits = float((amt_usd * Decimal("1")).quantize(Decimal("0.000001")))
                        add_credits(user_id, Decimal(str(credits)), reference=f"stripe:invoice:{data.get('id')}")
                        logger.info("credited user %s via invoice.paid %s credits", user_id, credits)
                    elif typ == "checkout.session.completed":
                        # If checkout used for one-off topup, PaymentIntent is nested:
                        if data.get("mode") == "payment":
                            pi = data.get("payment_intent")
                            try:
                                pi_obj = stripe.PaymentIntent.retrieve(pi)
                                amt_cents = int(pi_obj.amount or 0)
                                amt_usd = Decimal(amt_cents) / 100
                                credits = float((amt_usd * Decimal("1")).quantize(Decimal("0.000001")))
                                add_credits(user_id, Decimal(str(credits)), reference=f"stripe:checkout:{data.get('id')}")
                                logger.info("credited user %s via checkout payment %s credits", user_id, credits)
                            except Exception:
                                logger.exception("failed to retrieve payment intent in checkout.session.completed")
                        else:
                            # subscription completed: you probably want to enable plan on user
                            # when subscription created, you can attach plan name in metadata and update user.plan
                            sub = data.get("subscription")
                            try:
                                sub_obj = stripe.Subscription.retrieve(sub)
                                # example: attach plan name from price
                                price_id = sub_obj["items"]["data"][0]["price"]["id"]
                                # map price_id -> plan name (implement mapping in your settings or DB)
                                # For now, log it
                                logger.info("user %s subscription created price=%s", user_id, price_id)
                            except Exception:
                                logger.exception("error retrieving subscription")
                finally:
                    db.close()

        elif typ in ("charge.refunded", "charge.dispute.created"):
            # optionally handle refunds / disputes
            logger.info("stripe event %s received", typ)
        else:
            logger.debug("unhandled stripe event: %s", typ)
    except Exception:
        logger.exception("exception handling stripe webhook")

    # IMPORTANT: respond 2xx to acknowledge
    return JSONResponse({"ok": True}, status_code=200)
