# backend/app/api/v1/subscriptions.py
from fastapi import APIRouter, Depends, HTTPException, Request, Query
from typing import Optional
import stripe
from backend.app.config import settings
from backend.app.utils.security import get_current_user, get_current_admin
from backend.app.db import SessionLocal
from backend.app.models.user import User
from backend.app.services.stripe_handlers import cancel_subscription_on_stripe

router = APIRouter(prefix="/api/v1/subscriptions", tags=["subscriptions"])
stripe.api_key = settings.STRIPE_SECRET_KEY

def _get_user_by_current(current_user):
    # current_user is DB model object from get_current_user
    if not current_user:
        raise HTTPException(status_code=401, detail="auth_required")
    return current_user

@router.get("/my")
def list_my_subscriptions(current_user = Depends(get_current_user)):
    user = _get_user_by_current(current_user)
    if not getattr(user, "stripe_customer_id", None):
        return {"subscriptions": []}
    try:
        subs = stripe.Subscription.list(customer=user.stripe_customer_id, limit=100)
        return {"subscriptions": subs.data}
    except Exception as e:
        raise HTTPException(status_code=500, detail="stripe_error")

@router.post("/cancel")
def cancel_subscription(subscription_id: str, at_period_end: bool = Query(True), current_user = Depends(get_current_user)):
    user = _get_user_by_current(current_user)
    # basic permission: verify subscription belongs to user's customer (optional)
    try:
        # fetch subscription from stripe and ensure customer matches
        sub = stripe.Subscription.retrieve(subscription_id)
        if sub.customer != user.stripe_customer_id:
            raise HTTPException(status_code=403, detail="subscription_not_belong_to_user")
        result = cancel_subscription_on_stripe(subscription_id, at_period_end=at_period_end)
        return {"ok": True, "subscription": result}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail="stripe_cancel_failed")

# Admin routes
@router.post("/admin/cancel")
def admin_cancel(subscription_id: str, immediate: bool = Query(False), admin = Depends(get_current_admin)):
    try:
        sub = cancel_subscription_on_stripe(subscription_id, at_period_end=not immediate)
        return {"ok": True, "subscription": sub}
    except Exception as e:
        raise HTTPException(status_code=500, detail="stripe_cancel_failed")
