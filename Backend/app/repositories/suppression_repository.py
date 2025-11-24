from sqlalchemy import select
from backend.app.models import Suppression
from .base import BaseRepository


class SuppressionRepository(BaseRepository[Suppression]):
    def __init__(self, db):
        super().__init__(db, Suppression)

    async def is_suppressed(self, email: str) -> bool:
        result = await self.db.execute(
            select(Suppression).where(Suppression.email == email)
        )
        return result.scalar_one_or_none() is not None
