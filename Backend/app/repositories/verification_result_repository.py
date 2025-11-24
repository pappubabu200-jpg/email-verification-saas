from sqlalchemy import select
from backend.app.models import VerificationResult
from .base import BaseRepository


class VerificationResultRepository(BaseRepository[VerificationResult]):
    def __init__(self, db):
        super().__init__(db, VerificationResult)

    async def get_by_email(self, email: str):
        result = await self.db.execute(
            select(VerificationResult).where(VerificationResult.email == email)
        )
        return result.scalar_one_or_none()

    async def list_user_results(self, user_id: int, limit=200):
        result = await self.db.execute(
            select(VerificationResult)
            .where(VerificationResult.user_id == user_id)
            .limit(limit)
        )
        return result.scalars().all()
