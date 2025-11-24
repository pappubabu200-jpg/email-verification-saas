from sqlalchemy import select
from backend.app.models import CreditReservation
from .base import BaseRepository


class CreditReservationRepository(BaseRepository[CreditReservation]):
    def __init__(self, db):
        super().__init__(db, CreditReservation)

    async def get_by_job(self, job_id: str):
        result = await self.db.execute(
            select(CreditReservation).where(CreditReservation.job_id == job_id)
        )
        return result.scalar_one_or_none()
