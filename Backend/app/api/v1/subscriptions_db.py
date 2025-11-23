from fastapi import APIRouter, Depends, HTTPException
from backend.app.db import SessionLocal
from backend.app.utils.security import get_current_user, get_current_admin
from backend.app.models.subscription import Subscription

router = APIRouter(prefix="/api/v1/subscriptions-db", tags=["subscriptions-db"])

@router.get("/my")
def my_subscriptions(current_user = Depends(get_current_user)):
    db = SessionLocal()
    try:
        rows = db.query(Subscription).filter(
            Subscription.user_id == current_user.id
        ).all()
        return {"subscriptions": [serialize(s) for s in rows]}
    finally:
        db.close()


@router.get("/admin/all")
def admin_all_subscriptions(admin = Depends(get_current_admin)):
    db = SessionLocal()
    try:
        rows = db.query(Subscription).order_by(Subscription.created_at.desc()).all()
        return {"subscriptions": [serialize(s) for s in rows]}
    finally:
        db.close()


def serialize(s: Subscription):
    return {
        "id": s.id,
        "stripe_subscription_id": s.stripe_subscription_id,
        "user_id": s.user_id,
        "plan_name": s.plan_name,
        "status": s.status,
        "cancel_at_period_end": s.cancel_at_period_end,
        "price_amount": float(s.price_amount) if s.price_amount else None,
        "price_interval": s.price_interval,
        "current_period_start": str(s.current_period_start),
        "current_period_end": str(s.current_period_end),
}
