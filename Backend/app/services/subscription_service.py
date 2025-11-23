import logging
from backend.app.db import SessionLocal
from backend.app.models.subscription import Subscription
from backend.app.models.user import User
from backend.app.services.plan_service import get_plan_by_name

logger = logging.getLogger(__name__)

def upsert_subscription_from_stripe(sub: dict):
    """
    Create or update a subscription row from a Stripe webhook payload.
    """
    stripe_id = sub["id"]
    customer = sub["customer"]

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.stripe_customer_id == customer).first()
        if not user:
            logger.warning("Subscription webhook but customer user not found")
            return None

        existing = db.query(Subscription).filter(
            Subscription.stripe_subscription_id == stripe_id
        ).first()

        # determine plan name from metadata
        plan_name = None
        try:
            item = sub["items"]["data"][0]
            price_meta = item["price"].get("metadata", {})
            plan_name = price_meta.get("plan")
        except:
            pass

        if existing:
            existing.status = sub["status"]
            existing.plan_name = plan_name
            existing.cancel_at_period_end = sub.get("cancel_at_period_end", False)
            existing.price_amount = (sub["items"]["data"][0]["price"]["unit_amount"] / 100.0)
            existing.price_interval = sub["items"]["data"][0]["price"]["recurring"]["interval"]
            existing.current_period_start = sub["current_period_start"]
            existing.current_period_end = sub["current_period_end"]
            existing.raw = str(sub)
            db.commit()
            return existing

        # new subscription
        new = Subscription(
            stripe_subscription_id=stripe_id,
            stripe_customer_id=customer,
            user_id=user.id,
            plan_name=plan_name,
            status=sub["status"],
            cancel_at_period_end=sub.get("cancel_at_period_end", False),
            price_amount=(sub["items"]["data"][0]["price"]["unit_amount"] / 100.0),
            price_interval=sub["items"]["data"][0]["price"]["recurring"]["interval"],
            current_period_start=sub.get("current_period_start"),
            current_period_end=sub.get("current_period_end"),
            raw=str(sub)
        )

        db.add(new)

        # Assign plan to user automatically
        if plan_name:
            p = get_plan_by_name(plan_name)
            if p:
                user.plan = plan_name
                db.add(user)

        db.commit()
        return new

    except Exception as e:
        logger.exception("subscription upsert failed: %s", e)
        db.rollback()
    finally:
        db.close()


def delete_subscription_from_stripe(sub: dict):
    db = SessionLocal()
    try:
        stripe_id = sub["id"]
        row = db.query(Subscription).filter(
            Subscription.stripe_subscription_id == stripe_id
        ).first()
        if row:
            row.status = "canceled"
            db.add(row)
            db.commit()
    finally:
        db.close()
