
from sqlalchemy import select
from backend.app.models import UsageLog
from .base import BaseRepository


class UsageLogRepository(BaseRepository[UsageLog]):
    def __init__(self, db):
        super().__init__(db, UsageLog)

    async def list_user_usage(self, user_id: int, limit=200):
        result = await self.db.execute(
            select(UsageLog)
            .where(UsageLog.user_id == user_id)
            .limit(limit)
        )
        return result.scalars().all()

    async def list_api_key_usage(self, api_key_id: int, limit=200):
        result = await self.db.execute(
            select(UsageLog)
            .where(UsageLog.api_key_id == api_key_id)
            .limit(limit)
        )
        return result.scalars().all()
