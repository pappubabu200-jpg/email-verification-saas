# backend/app/routers/suppression.py

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db import async_session
from backend.app.services.auth_service import get_current_user
from backend.app.repositories.suppression_repository import SuppressionRepository
from backend.app.schemas.suppression import SuppressionResponse

router = APIRouter(prefix="/suppression", tags=["suppression"])


async def get_db():
    async with async_session() as session:
        yield session


# ---------------------------------------
# Add suppressed email
# ---------------------------------------
@router.post("/add", response_model=SuppressionResponse)
async def add_suppressed(
    email: str,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    repo = SuppressionRepository(db)

    suppressed = await repo.create({
        "email": email.lower().strip(),
        "reason": "manual"
    })

    return SuppressionResponse.from_orm(suppressed)


# ---------------------------------------
# List suppressed emails
# ---------------------------------------
@router.get("/", response_model=list[SuppressionResponse])
async def list_suppressed(
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    repo = SuppressionRepository(db)
    items = await repo.all()
    return [SuppressionResponse.from_orm(i) for i in items]


# ---------------------------------------
# Remove suppressed email
# ---------------------------------------
@router.delete("/{email}")
async def delete_suppressed(
    email: str,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    repo = SuppressionRepository(db)
    suppressed = await repo.get_by_email(email)

    if not suppressed:
        raise HTTPException(404, "Email not found in suppression list")

    await repo.delete(suppressed)
    return {"removed": True}
