from sqlalchemy import select
from backend.app.models import WebhookEndpoint
from .base import BaseRepository


class WebhookEndpointRepository(BaseRepository[WebhookEndpoint]):
    def __init__(self, db):
        super().__init__(db, WebhookEndpoint)

    async def get_user_endpoints(self, user_id: int):
        result = await self.db.execute(
            select(WebhookEndpoint).where(WebhookEndpoint.user_id == user_id)
        )
        return result.scalars().all()

    async def get_by_secret(self, secret: str):
        result = await self.db.execute(
            select(WebhookEndpoint).where(WebhookEndpoint.secret == secret)
        )
        return result.scalar_one_or_none()
