# backend/app/routers/usage_logs.py

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db import async_session
from backend.app.services.auth_service import get_current_user
from backend.app.repositories.usage_log_repository import UsageLogRepository

router = APIRouter(prefix="/usage", tags=["usage-logs"])


async def get_db():
    async with async_session() as session:
        yield session


@router.get("/")
async def get_usage_logs(
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    repo = UsageLogRepository(db)
    logs = await repo.get_user_logs(current_user.id)
    return logs
