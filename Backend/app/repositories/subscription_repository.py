
from sqlalchemy import select
from backend.app.models import Subscription
from .base import BaseRepository


class SubscriptionRepository(BaseRepository[Subscription]):
    def __init__(self, db):
        super().__init__(db, Subscription)

    async def get_by_stripe_subscription_id(self, stripe_id: str):
        result = await self.db.execute(
            select(Subscription).where(Subscription.stripe_subscription_id == stripe_id)
        )
        return result.scalar_one_or_none()

    async def get_user_active_subscription(self, user_id: int):
        result = await self.db.execute(
            select(Subscription)
            .where(Subscription.user_id == user_id)
            .where(Subscription.status == "active")
        )
        return result.scalar_one_or_none()
