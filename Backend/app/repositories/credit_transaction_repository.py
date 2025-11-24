from sqlalchemy import select
from backend.app.models import CreditTransaction
from .base import BaseRepository


class CreditTransactionRepository(BaseRepository[CreditTransaction]):
    def __init__(self, db):
        super().__init__(db, CreditTransaction)

    async def list_user_transactions(self, user_id: int, limit=100):
        result = await self.db.execute(
            select(CreditTransaction)
            .where(CreditTransaction.user_id == user_id)
            .limit(limit)
        )
        return result.scalars().all()
