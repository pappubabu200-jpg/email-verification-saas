
from sqlalchemy import select
from backend.app.models import Team
from .base import BaseRepository


class TeamRepository(BaseRepository[Team]):
    def __init__(self, db):
        super().__init__(db, Team)

    async def get_by_owner(self, user_id: int):
        result = await self.db.execute(select(Team).where(Team.owner_id == user_id))
        return result.scalars().all()
