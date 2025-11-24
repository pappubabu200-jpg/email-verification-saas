# backend/app/routers/decision_maker.py

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db import async_session
from backend.app.services.auth_service import get_current_user
from backend.app.repositories.decision_maker_repository import DecisionMakerRepository
from backend.app.schemas.decision_maker import DecisionMakerResponse

router = APIRouter(prefix="/decision-maker", tags=["decision-maker"])


async def get_db():
    async with async_session() as session:
        yield session


# ---------------------------------------
# Store decision maker record
# ---------------------------------------
@router.post("/add", response_model=DecisionMakerResponse)
async def add_decision_maker(
    company: str,
    email: str,
    first_name: str | None = None,
    last_name: str | None = None,
    title: str | None = None,
    source: str | None = None,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    repo = DecisionMakerRepository(db)

    dm = await repo.create({
        "user_id": current_user.id,
        "company": company,
        "email": email,
        "first_name": first_name,
        "last_name": last_name,
        "title": title,
        "source": source
    })

    return DecisionMakerResponse.from_orm(dm)


# ---------------------------------------
# List user decision makers
# ---------------------------------------
@router.get("/", response_model=list[DecisionMakerResponse])
async def list_decision_makers(
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    repo = DecisionMakerRepository(db)
    dms = await repo.get_by_user(current_user.id)
    return [DecisionMakerResponse.from_orm(i) for i in dms]
