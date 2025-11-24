from sqlalchemy import select
from backend.app.models import DomainCache
from .base import BaseRepository


class DomainCacheRepository(BaseRepository[DomainCache]):
    def __init__(self, db):
        super().__init__(db, DomainCache)

    async def get_by_domain(self, domain: str):
        result = await self.db.execute(
            select(DomainCache).where(DomainCache.domain == domain)
        )
        return result.scalar_one_or_none()
