from sqlalchemy import select
from backend.app.models import FailedJob
from .base import BaseRepository


class FailedJobRepository(BaseRepository[FailedJob]):
    def __init__(self, db):
        super().__init__(db, FailedJob)

    async def get_recent_failures(self, limit=100):
        result = await self.db.execute(
            select(FailedJob).order_by(FailedJob.id.desc()).limit(limit)
        )
        return result.scalars().all()
