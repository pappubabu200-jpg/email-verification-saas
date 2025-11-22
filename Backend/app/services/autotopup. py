
from backend.app.config import settings
import stripe
from backend.app.db import SessionLocal
from backend.app.models.user import User
from backend.app.services.credits_service import add_credits
from decimal import Decimal
import logging

logger = logging.getLogger(__name__)
stripe.api_key = settings.STRIPE_SECRET_KEY

AUTO_TOPUP_THRESHOLD = Decimal(getattr(settings, "AUTO_TOPUP_THRESHOLD", "10.0"))
AUTO_TOPUP_AMOUNT = Decimal(getattr(settings, "AUTO_TOPUP_AMOUNT", "50.0"))

def maybe_autotopup_user(user_id: int):
    db = SessionLocal()
    try:
        u = db.query(User).get(user_id)
        if not u:
            return False
        balance = Decimal(getattr(u, "credits", 0) or 0)
        if balance < AUTO_TOPUP_THRESHOLD:
            # initiate Stripe payment flow or charge saved card for user (must implement)
            # here we assume u.stripe_customer_id exists and there is a default payment method
            try:
                ch = stripe.PaymentIntent.create(
                    amount=int(AUTO_TOPUP_AMOUNT * 100),
                    currency="usd",
                    customer=u.stripe_customer_id,
                    payment_method=u.default_payment_method_id,  # you must store this
                    off_session=True,
                    confirm=True
                )
                # on success, add credits
                add_credits(u.id, AUTO_TOPUP_AMOUNT, reference=f"autotopup:{ch['id']}")
                return True
            except Exception as e:
                logger.exception("autotopup failed: %s", e)
                return False
    finally:
        db.close()
