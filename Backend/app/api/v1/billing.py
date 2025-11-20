from fastapi import APIRouter, Depends, Request, Header, HTTPException
from pydantic import BaseModel
from decimal import Decimal
import os

from sqlalchemy.orm import Session
from backend.app.db import SessionLocal
from backend.app.utils.security import get_current_user
from backend.app.services.billing_service import create_stripe_checkout_session, handle_stripe_payment_intent
from backend.app.services.credits_service import get_balance, add_credits
from backend.app.models.credit_transaction import CreditTransaction

router = APIRouter(prefix="/v1/billing", tags=["Billing"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


class TopupIn(BaseModel):
    amount_in_inr: int
    credits: Decimal = None


@router.post("/topup")
def topup(payload: TopupIn, current_user = Depends(get_current_user)):
    """
    Initiate a Stripe Checkout Session (test mode). Provide success/cancel URLs as env or query in real app.
    Returns session url (client should redirect).
    NOTE: requires STRIPE_SECRET_KEY in .env.
    """
    session = create_stripe_checkout_session(payload.amount_in_inr, currency="inr")
    return session


@router.get("/balance")
def balance(current_user = Depends(get_current_user), db: Session = Depends(get_db)):
    bal = get_balance(db, current_user.id)
    return {"balance": float(bal)}


@router.post("/webhook")
async def stripe_webhook(request: Request, stripe_signature: str = Header(None)):
    """
    Generic webhook endpoint for Stripe (you should verify signature in prod).
    This route will call billing_service.handle_stripe_payment_intent and credit the user if metadata present.
    """
    payload = await request.body()
    # try to parse JSON
    try:
        event = await request.json()
    except Exception:
        # fallback parse from raw
        import json
        event = json.loads(payload.decode("utf-8", errors="ignore"))

    # If STRIPE_WEBHOOK_SECRET set, verify signature (not implemented here, keep simple)
    try:
        handled = handle_stripe_payment_intent(event)
        if handled:
            return {"status": "ok"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return {"status": "ignored"}
