# backend/app/api/v1/checkout.py
import stripe
import uuid
from fastapi import APIRouter, Depends, HTTPException, Request
from backend.app.utils.security import get_current_user
from backend.app.config import settings
from backend.app.db import SessionLocal
from backend.app.models.user import User
from backend.app.services.plan_service import get_plan_by_name

router = APIRouter(prefix="/api/v1/checkout", tags=["checkout"])

stripe.api_key = settings.STRIPE_SECRET_KEY


# ---------------------------------------------------------
# Ensure Stripe Customer Exists
# ---------------------------------------------------------
def _ensure_customer(user: User):
    if user.stripe_customer_id:
        return user.stripe_customer_id

    customer = stripe.Customer.create(
        email=user.email,
        metadata={"user_id": user.id}
    )
    db = SessionLocal()
    try:
        user.stripe_customer_id = customer.id
        db.add(user)
        db.commit()
    finally:
        db.close()

    return customer.id


# ---------------------------------------------------------
# 1) CREATE TOP-UP (buy credits)
# ---------------------------------------------------------
@router.post("/topup")
def create_topup(request: Request, credits: int, current_user = Depends(get_current_user)):
    """
    Create Stripe Checkout Session for buying credits.
    credits = number of credits (integer)
    """
    user = current_user
    if not user:
        raise HTTPException(status_code=401, detail="auth_required")

    if credits <= 0:
        raise HTTPException(status_code=400, detail="credits_must_be_positive")

    # price logic: $1 = 100 credits (example)
    price_per_credit = float(getattr(settings, "PRICE_PER_CREDIT", 0.01))
    amount = int(credits * price_per_credit * 100)  # Stripe uses cents

    customer_id = _ensure_customer(user)

    session = stripe.checkout.Session.create(
        mode="payment",
        customer=customer_id,
        payment_method_types=["card"],
        line_items=[{
            "price_data": {
                "currency": "usd",
                "unit_amount": amount,
                "product_data": {
                    "name": f"{credits} Credits"
                },
            },
            "quantity": 1,
        }],
        metadata={
            "user_id": str(user.id),
            "topup_credits": str(credits)
        },
        success_url=f"{settings.FRONTEND_URL}/billing/success",
        cancel_url=f"{settings.FRONTEND_URL}/billing/cancel",
    )

    return {"checkout_url": session.url}


# ---------------------------------------------------------
# 2) SUBSCRIPTION CHECKOUT
# ---------------------------------------------------------
@router.post("/subscribe")
def create_subscription(request: Request, plan_name: str, current_user = Depends(get_current_user)):
    """
    Create Stripe subscription checkout session for a plan.
    plan_name = free | pro | team | enterprise
    """
    user = current_user
    if not user:
        raise HTTPException(status_code=401, detail="auth_required")

    plan = get_plan_by_name(plan_name)
    if not plan:
        raise HTTPException(status_code=404, detail="plan_not_found")

    if float(plan.monthly_price_usd) <= 0:
        raise HTTPException(status_code=400, detail="plan_not_subscribable")

    customer_id = _ensure_customer(user)

    # Stripe product creation flow
    product = stripe.Product.create(name=f"{plan.display_name} Subscription")

    price = stripe.Price.create(
        product=product.id,
        unit_amount=int(float(plan.monthly_price_usd) * 100),
        currency="usd",
        recurring={"interval": "month"},
    )

    session = stripe.checkout.Session.create(
        mode="subscription",
        customer=customer_id,
        payment_method_types=["card"],
        line_items=[{
            "price": price.id,
            "quantity": 1
        }],
        metadata={
            "user_id": str(user.id),
            "plan": plan.name,
        },
        success_url=f"{settings.FRONTEND_URL}/billing/success",
        cancel_url=f"{settings.FRONTEND_URL}/billing/cancel",
    )

    return {"checkout_url": session.url}
