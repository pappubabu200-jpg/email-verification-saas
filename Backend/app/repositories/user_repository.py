from sqlalchemy import select
from backend.app.models import User
from .base import BaseRepository


class UserRepository(BaseRepository[User]):
    def __init__(self, db):
        super().__init__(db, User)

    async def get_by_email(self, email: str):
        result = await self.db.execute(select(User).where(User.email == email))
        return result.scalar_one_or_none()
