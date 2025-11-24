from sqlalchemy import select
from backend.app.models import BulkJob
from .base import BaseRepository


class BulkJobRepository(BaseRepository[BulkJob]):
    def __init__(self, db):
        super().__init__(db, BulkJob)

    async def get_by_job_id(self, job_id: str):
        result = await self.db.execute(
            select(BulkJob).where(BulkJob.job_id == job_id)
        )
        return result.scalar_one_or_none()

    async def list_user_jobs(self, user_id: int):
        result = await self.db.execute(
            select(BulkJob).where(BulkJob.user_id == user_id)
        )
        return result.scalars().all()
