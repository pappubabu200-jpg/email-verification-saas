
from sqlalchemy import select
from backend.app.models import Plan
from .base import BaseRepository


class PlanRepository(BaseRepository[Plan]):
    def __init__(self, db):
        super().__init__(db, Plan)

    async def get_by_name(self, name: str):
        result = await self.db.execute(select(Plan).where(Plan.name == name))
        return result.scalar_one_or_none()

    async def list_public_plans(self):
        result = await self.db.execute(
            select(Plan).where(Plan.is_public == True)
        )
        return result.scalars().all()
