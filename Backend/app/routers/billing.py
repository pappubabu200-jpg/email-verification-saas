# backend/app/routers/billing.py

import os
import stripe
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db import async_session
from backend.app.services.auth_service import get_current_user
from backend.app.repositories.subscription_repository import SubscriptionRepository
from backend.app.repositories.plan_repository import PlanRepository
from backend.app.schemas.subscription import SubscriptionResponse

router = APIRouter(prefix="/billing", tags=["billing"])

stripe.api_key = os.getenv("STRIPE_SECRET")


# ---------------------------------------
# DB dependency
# ---------------------------------------
async def get_db():
    async with async_session() as session:
        yield session


# ---------------------------------------------------------
# POST /billing/create-checkout-session
# Creates Stripe Checkout session
# ---------------------------------------------------------
@router.post("/create-checkout-session")
async def create_checkout_session(
    plan_id: int,
    current_user = Depends(get_current_user),
    request: Request = None,
    db: AsyncSession = Depends(get_db)
):
    plan_repo = PlanRepository(db)
    plan = await plan_repo.get(plan_id)

    if not plan:
        raise HTTPException(404, "Plan not found.")

    # Ensure Stripe customer exists
    if not current_user.stripe_customer_id:
        customer = stripe.Customer.create(
            email=current_user.email,
            metadata={"user_id": current_user.id}
        )
        current_user.stripe_customer_id = customer.id

    # Create checkout session
    session = stripe.checkout.Session.create(
        customer=current_user.stripe_customer_id,
        mode="subscription",
        line_items=[{
            "price_data": {
                "currency": "usd",
                "product_data": {"name": plan.display_name},
                "unit_amount": int(plan.monthly_price_usd * 100),
                "recurring": {"interval": "month"},
            },
            "quantity": 1,
        }],
        success_url=f"{os.getenv('FRONTEND_URL')}/billing/success",
        cancel_url=f"{os.getenv('FRONTEND_URL')}/billing/cancel",
        metadata={"user_id": current_user.id, "plan_id": plan.id},
    )

    return {"checkout_url": session.url}


# ---------------------------------------------------------
# POST /billing/customer-portal
# Opens Stripe Billing Portal
# ---------------------------------------------------------
@router.post("/customer-portal")
async def customer_portal(
    current_user = Depends(get_current_user)
):
    if not current_user.stripe_customer_id:
        raise HTTPException(400, "User has no Stripe customer account.")

    portal = stripe.billing_portal.Session.create(
        customer=current_user.stripe_customer_id,
        return_url=os.getenv("FRONTEND_URL", "https://yourapp.com/dashboard"),
    )
    return {"portal_url": portal.url}


# ---------------------------------------------------------
# GET /billing/subscription → Get current subscription
# ---------------------------------------------------------
@router.get("/subscription", response_model=list[SubscriptionResponse])
async def get_subscription(
    current_user = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    repo = SubscriptionRepository(db)
    subs = await repo.get_user_subscriptions(current_user.id)
    return [SubscriptionResponse.from_orm(s) for s in subs]


# ---------------------------------------------------------
# POST /billing/cancel → Cancel Subscription
# ---------------------------------------------------------
@router.post("/cancel")
async def cancel_subscription(
    subscription_id: int,
    current_user = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    repo = SubscriptionRepository(db)
    subscription = await repo.get(subscription_id)

    if not subscription or subscription.user_id != current_user.id:
        raise HTTPException(404, "Subscription not found.")

    stripe.Subscription.modify(
        subscription.stripe_subscription_id,
        cancel_at_period_end=True
    )

    await repo.update(subscription, {"cancel_at_period_end": True})

    return {"cancel_requested": True}


# ---------------------------------------------------------
# GET /billing/invoices → List invoices
# ---------------------------------------------------------
@router.get("/invoices")
async def list_invoices(
    current_user = Depends(get_current_user)
):
    if not current_user.stripe_customer_id:
        return []

    invoices = stripe.Invoice.list(
        customer=current_user.stripe_customer_id
    )

    return invoices


# ---------------------------------------------------------
# STRIPE WEBHOOK HANDLER
# ---------------------------------------------------------
@router.post("/webhook")
async def stripe_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    webhook_secret = os.getenv("STRIPE_WEBHOOK_SECRET")

    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, webhook_secret
        )
    except Exception:
        raise HTTPException(400, "Invalid webhook")

    event_type = event["type"]
    data = event["data"]["object"]

    repo = SubscriptionRepository(db)

    # -----------------------------------
    # SUBSCRIPTION CREATED / UPDATED
    # -----------------------------------
    if event_type in (
        "customer.subscription.created",
        "customer.subscription.updated",
        "customer.subscription.resumed",
    ):
        sub_id = data["id"]
        customer = data["customer"]
        status = data["status"]
        plan_amount = data["items"]["data"][0]["price"]["unit_amount"] / 100

        # Save subscription in DB
        await repo.upsert_subscription_from_stripe(
            stripe_subscription_id=sub_id,
            stripe_customer_id=customer,
            status=status,
            plan_amount=plan_amount,
            current_period_start=data.get("current_period_start"),
            current_period_end=data.get("current_period_end"),
            cancel_at_period_end=data.get("cancel_at_period_end")
        )

    # -----------------------------------
    # SUBSCRIPTION CANCELLED
    # -----------------------------------
    elif event_type == "customer.subscription.deleted":
        sub_id = data["id"]
        subscription = await repo.get_by_stripe_id(sub_id)

        if subscription:
            await repo.update(subscription, {"status": "canceled"})

    # -----------------------------------
    # PAYMENT SUCCEEDED
    # -----------------------------------
    elif event_type == "invoice.payment_succeeded":
        pass  # optional: add logic for credit allocation

    return {"received": True}
