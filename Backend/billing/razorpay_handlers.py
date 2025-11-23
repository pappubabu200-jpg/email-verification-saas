# backend/app/billing/razorpay_handlers.py
import os
import razorpay
import logging
from fastapi import APIRouter, Request, Depends, HTTPException
from backend.app.utils.security import get_current_user
from backend.app.services.credits_service import add_credits
from decimal import Decimal

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/billing/razorpay", tags=["razorpay"])

RAZORPAY_KEY_ID = os.getenv("RAZORPAY_KEY_ID", "")
RAZORPAY_KEY_SECRET = os.getenv("RAZORPAY_KEY_SECRET", "")
razor = razorpay.Client(auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET))

@router.post("/create-order")
async def create_order(request: Request, current_user = Depends(get_current_user)):
    payload = await request.json()
    amount_inr = payload.get("amount_inr")
    if not amount_inr:
        raise HTTPException(status_code=400, detail="amount_inr required")
    # razorpay expects paise
    amount_paise = int(Decimal(str(amount_inr)) * 100)
    order = razor.order.create({"amount": amount_paise, "currency": "INR", "receipt": f"topup_{current_user.id}_{int(amount_paise)}"})
    return {"order": order}

@router.post("/webhook")
async def razorpay_webhook(request: Request):
    # Implement signature verification and credit user on payment captured.
    # The Razorpay webhook body contains "payload" with payment entity; use header 'x-razorpay-signature' to verify.
    body = await request.body()
    sig = request.headers.get("x-razorpay-signature")
    # verify with razorpay util (if available) or your own HMAC
    try:
        data = await request.json()
    except Exception:
        return {"ok": False}
    # This is a simple handler: if event 'payment.captured', fetch metadata and credit user
    event = data.get("event")
    if event == "payment.captured":
        payment = data.get("payload", {}).get("payment", {}).get("entity", {})
        # if you stored user_id in notes or receipt, extract and credit
        notes = payment.get("notes") or {}
        user_id = notes.get("user_id") or None
        amount = payment.get("amount")  # in paise
        if user_id and amount:
            try:
                usd_equiv = Decimal(amount) / Decimal(100)  # rupees; adapt conversion as needed
                # map INR->credits (policy)
                add_credits(int(user_id), usd_equiv, reference=f"razorpay:{payment.get('id')}")
            except Exception:
                logger.exception("razor webhook credit failed")
    return {"ok": True}
