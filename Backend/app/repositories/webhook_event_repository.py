from sqlalchemy import select
from backend.app.models import WebhookEvent
from .base import BaseRepository


class WebhookEventRepository(BaseRepository[WebhookEvent]):
    def __init__(self, db):
        super().__init__(db, WebhookEvent)

    async def list_recent(self, limit=100):
        result = await self.db.execute(
            select(WebhookEvent).order_by(WebhookEvent.id.desc()).limit(limit)
        )
        return result.scalars().all()
