
from sqlalchemy import select
from backend.app.models import ApiKey
from .base import BaseRepository


class ApiKeyRepository(BaseRepository[ApiKey]):
    def __init__(self, db):
        super().__init__(db, ApiKey)

    async def get_by_hash(self, key_hash: str):
        result = await self.db.execute(select(ApiKey).where(ApiKey.key_hash == key_hash))
        return result.scalar_one_or_none()

    async def get_user_keys(self, user_id: int):
        result = await self.db.execute(select(ApiKey).where(ApiKey.user_id == user_id))
        return result.scalars().all()
