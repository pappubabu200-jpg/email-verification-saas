
# backend/app/api/v1/billing_dashboard.py
from fastapi import APIRouter, Depends, Query, HTTPException
from backend.app.utils.security import get_current_admin
from backend.app.config import settings
import stripe
from datetime import datetime, timedelta

router = APIRouter(prefix="/api/v1/admin/billing", tags=["admin-billing"])
stripe.api_key = settings.STRIPE_SECRET_KEY

@router.get("/summary")
def billing_summary(days:int = Query(30), admin=Depends(get_current_admin)):
    """
    Returns:
      - active_subscriptions
      - canceled_subscriptions (last N days)
      - MRR estimate (sum of recurring price amounts monthly)
    """
    try:
        # Active subscriptions
        active = stripe.Subscription.list(status="active", limit=1000)
        active_subs = active.data

        # canceled in last N days
        since = int((datetime.utcnow() - timedelta(days=days)).timestamp())
        canceled = stripe.Subscription.list(status="canceled", limit=1000)
        canceled_recent = [s for s in canceled.data if s.canceled_at and int(s.canceled_at) >= since]

        # estimate MRR: sum of recurring prices monthly
        mrr = 0
        for s in active_subs:
            try:
                # take price from first item
                items = s["items"]["data"]
                if not items:
                    continue
                price = items[0].get("price") or {}
                unit_amount = price.get("unit_amount") or 0
                interval = price.get("recurring", {}).get("interval", "month")
                if interval == "month":
                    mrr += (unit_amount / 100.0)
                elif interval == "year":
                    mrr += (unit_amount / 100.0) / 12.0
            except Exception:
                continue

        return {
            "active_subscriptions": len(active_subs),
            "canceled_recent": len(canceled_recent),
            "mrr_usd": round(mrr, 2)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail="stripe_api_error")
