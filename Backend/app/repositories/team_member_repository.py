from sqlalchemy import select
from backend.app.models import TeamMember
from .base import BaseRepository


class TeamMemberRepository(BaseRepository[TeamMember]):
    def __init__(self, db):
        super().__init__(db, TeamMember)

    async def get_team_members(self, team_id: int):
        result = await self.db.execute(select(TeamMember).where(TeamMember.team_id == team_id))
        return result.scalars().all()

    async def get_user_teams(self, user_id: int):
        result = await self.db.execute(select(TeamMember).where(TeamMember.user_id == user_id))
        return result.scalars().all()
