# backend/app/services/auto_topup.py

import logging
from decimal import Decimal

import stripe
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.config import settings
from backend.app.db import async_session
from backend.app.models.user import User
from backend.app.services.credits_service import add_credits

logger = logging.getLogger(__name__)

stripe.api_key = settings.STRIPE_SECRET_KEY

AUTO_TOPUP_THRESHOLD = Decimal(str(getattr(settings, "AUTO_TOPUP_THRESHOLD", "10.0")))
AUTO_TOPUP_AMOUNT = Decimal(str(getattr(settings, "AUTO_TOPUP_AMOUNT", "50.0")))


# -------------------------------------------------------------
# ASYNC TOP-UP LOGIC
# -------------------------------------------------------------
async def maybe_autotopup_user(user_id: int) -> bool:
    """
    Checks user credit balance → If below threshold, run auto-topup.

    Returns:
        True  = top-up completed
        False = not triggered or failed
    """

    async with async_session() as db:
        # Fetch user
        q = await db.execute(select(User).where(User.id == user_id))
        user = q.scalar_one_or_none()

        if not user:
            logger.warning(f"Auto-topup: user {user_id} not found")
            return False

        balance = Decimal(str(user.credits or 0))

        # Already sufficient balance
        if balance >= AUTO_TOPUP_THRESHOLD:
            return False

        # Check Stripe billing setup
        if not user.stripe_customer_id:
            logger.warning(f"Auto-topup skipped: no stripe_customer_id for user {user.id}")
            return False

        if not getattr(user, "default_payment_method_id", None):
            logger.warning(f"Auto-topup skipped: no default payment method for user {user.id}")
            return False

        try:
            # ---------------------------------------------------------
            # Create PaymentIntent
            # ---------------------------------------------------------
            intent = stripe.PaymentIntent.create(
                amount=int(AUTO_TOPUP_AMOUNT * 100),   # cents
                currency="usd",
                customer=user.stripe_customer_id,
                payment_method=user.default_payment_method_id,
                off_session=True,
                confirm=True,
            )

            logger.info(f"Auto-topup success for user {user.id}: PI={intent['id']}")

            # ---------------------------------------------------------
            # Add credits
            # ---------------------------------------------------------
            await add_credits(
                user_id=user.id,
                amount=AUTO_TOPUP_AMOUNT,
                reference=f"auto_topup:{intent['id']}",
            )

            return True

        except stripe.error.CardError as e:
            logger.error(f"Auto-topup card declined for user {user.id}: {e}")
            return False

        except Exception as e:
            logger.exception(f"Auto-topup failed for user {user.id}: {e}")
            return False
