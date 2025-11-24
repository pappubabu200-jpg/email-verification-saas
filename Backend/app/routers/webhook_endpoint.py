# backend/app/routers/webhook_endpoint.py

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db import async_session
from backend.app.services.auth_service import get_current_user
from backend.app.repositories.webhook_endpoint_repository import WebhookEndpointRepository
from backend.app.schemas.webhook_endpoint import WebhookEndpointResponse

router = APIRouter(prefix="/webhooks", tags=["webhook-endpoints"])


async def get_db():
    async with async_session() as session:
        yield session


# ---------------------------------------
# Create webhook endpoint
# ---------------------------------------
@router.post("/create", response_model=WebhookEndpointResponse)
async def create_webhook(
    url: str,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    repo = WebhookEndpointRepository(db)
    wh = await repo.create({
        "user_id": current_user.id,
        "url": url
    })
    return WebhookEndpointResponse.from_orm(wh)


# ---------------------------------------
# List endpoints
# ---------------------------------------
@router.get("/", response_model=list[WebhookEndpointResponse])
async def list_webhooks(
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    repo = WebhookEndpointRepository(db)
    items = await repo.get_user_endpoints(current_user.id)
    return [WebhookEndpointResponse.from_orm(i) for i in items]


# ---------------------------------------
# Delete endpoint
# ---------------------------------------
@router.delete("/{id}")
async def delete_webhook(
    id: int,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    repo = WebhookEndpointRepository(db)
    wh = await repo.get(id)

    if not wh or wh.user_id != current_user.id:
        raise HTTPException(404, "Webhook endpoint not found")

    await repo.delete(wh)
    return {"deleted": True}
