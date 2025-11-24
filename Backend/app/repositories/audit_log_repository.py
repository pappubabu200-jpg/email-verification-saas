from sqlalchemy import select
from backend.app.models import AuditLog
from .base import BaseRepository


class AuditLogRepository(BaseRepository[AuditLog]):
    def __init__(self, db):
        super().__init__(db, AuditLog)

    async def list_user_logs(self, user_id: int, limit=200):
        result = await self.db.execute(
            select(AuditLog)
            .where(AuditLog.user_id == user_id)
            .limit(limit)
        )
        return result.scalars().all()

    async def list_team_logs(self, team_id: int, limit=200):
        result = await self.db.execute(
            select(AuditLog)
            .where(AuditLog.team_id == team_id)
            .limit(limit)
        )
        return result.scalars().all()
