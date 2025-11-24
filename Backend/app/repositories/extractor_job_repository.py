from sqlalchemy import select
from backend.app.models import ExtractorJob
from .base import BaseRepository


class ExtractorJobRepository(BaseRepository[ExtractorJob]):
    def __init__(self, db):
        super().__init__(db, ExtractorJob)

    async def get_by_job_id(self, job_id: str):
        result = await self.db.execute(
            select(ExtractorJob).where(ExtractorJob.job_id == job_id)
        )
        return result.scalar_one_or_none()
