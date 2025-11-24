# backend/app/routers/webhook_event.py

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db import async_session
from backend.app.services.auth_service import get_current_user
from backend.app.repositories.webhook_event_repository import WebhookEventRepository

router = APIRouter(prefix="/webhook-events", tags=["webhook-events"])


async def get_db():
    async with async_session() as session:
        yield session


@router.get("/")
async def get_user_webhook_events(
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    repo = WebhookEventRepository(db)
    events = await repo.get_by_user(current_user.id)
    return events
