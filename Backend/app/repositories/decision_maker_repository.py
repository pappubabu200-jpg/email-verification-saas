from sqlalchemy import select
from backend.app.models import DecisionMaker
from .base import BaseRepository


class DecisionMakerRepository(BaseRepository[DecisionMaker]):
    def __init__(self, db):
        super().__init__(db, DecisionMaker)

    async def find_by_domain(self, domain: str):
        result = await self.db.execute(
            select(DecisionMaker).where(DecisionMaker.domain == domain)
        )
        return result.scalars().all()
