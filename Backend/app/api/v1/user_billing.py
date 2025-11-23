# backend/app/api/v1/user_billing.py
from fastapi import APIRouter, Depends, HTTPException
from backend.app.utils.security import get_current_user
from backend.app.db import SessionLocal
from backend.app.models.user import User
import stripe
from backend.app.config import settings

stripe.api_key = settings.STRIPE_SECRET_KEY

router = APIRouter(prefix="/api/v1/billing/me", tags=["user-billing"])

@router.get("/subscription")
def my_subscription(current_user = Depends(get_current_user)):
    db = SessionLocal()
    try:
        u = db.query(User).get(current_user.id)
        if not u:
            raise HTTPException(404, "user_not_found")
        # fetch subscription via stripe if stripe_customer_id present
        if u.stripe_customer_id:
            subs = stripe.Subscription.list(customer=u.stripe_customer_id, limit=10)
            return {"stripe_subscriptions": subs.data}
        return {"stripe_subscriptions": []}
    finally:
        db.close()

@router.get("/invoices")
def my_invoices(current_user = Depends(get_current_user)):
    db = SessionLocal()
    try:
        u = db.query(User).get(current_user.id)
        if not u:
            raise HTTPException(404, "user_not_found")
        if u.stripe_customer_id:
            inv = stripe.Invoice.list(customer=u.stripe_customer_id, limit=24)
            return {"invoices": [ {"id": i.id, "amount_due": i.amount_due, "status": i.status, "hosted_invoice_url": i.hosted_invoice_url} for i in inv.data ]}
        return {"invoices": []}
    finally:
        db.close()

@router.get("/credits")
def my_credits(current_user = Depends(get_current_user)):
    db = SessionLocal()
    try:
        u = db.query(User).get(current_user.id)
        return {"credits": float(getattr(u, "credits", 0))}
    finally:
        db.close()
