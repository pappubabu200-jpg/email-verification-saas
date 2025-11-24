
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Type, TypeVar, Generic, Optional

ModelType = TypeVar("ModelType")


class BaseRepository(Generic[ModelType]):
    def __init__(self, db: AsyncSession, model: Type[ModelType]):
        self.db = db
        self.model = model

    async def get(self, id: int) -> Optional[ModelType]:
        result = await self.db.execute(select(self.model).where(self.model.id == id))
        return result.scalar_one_or_none()

    async def list(self, limit: int = 100, skip: int = 0):
        result = await self.db.execute(
            select(self.model).offset(skip).limit(limit)
        )
        return result.scalars().all()

    async def create(self, obj_data: dict) -> ModelType:
        obj = self.model(**obj_data)
        self.db.add(obj)
        await self.db.commit()
        await self.db.refresh(obj)
        return obj

    async def update(self, obj: ModelType, update_data: dict) -> ModelType:
        for field, value in update_data.items():
            setattr(obj, field, value)
        self.db.add(obj)
        await self.db.commit()
        await self.db.refresh(obj)
        return obj

    async def delete(self, obj: ModelType):
        await self.db.delete(obj)
        await self.db.commit()
        return True
