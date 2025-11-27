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

# backend/app/routers/decision_maker.py
from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Optional
from backend.app.services.decision_maker_service import search_decision_makers, get_decision_maker_detail
from backend.app.utils.security import get_current_user_optional  # adapt to your auth helper

router = APIRouter(prefix="/decision-maker", tags=["decision_maker"])


@router.get("/search")
async def dm_search(q: str = Query(..., min_length=2), limit: int = Query(10, ge=1, le=50), user=Depends(get_current_user_optional)):
    user_id = getattr(user, "id", None) if user else None
    try:
        results = await search_decision_makers(q, user_id=user_id, limit=limit)
        return {"results": results}
    except Exception as e:
        raise HTTPException(status_code=429 if "Rate limit" in str(e) else 500, detail=str(e))


@router.get("/{uid}")
async def dm_detail(uid: str, user=Depends(get_current_user_optional)):
    user_id = getattr(user, "id", None) if user else None
    try:
        detail = await get_decision_maker_detail(uid, user_id=user_id)
        if not detail:
            raise HTTPException(status_code=404, detail="Not found")
        return detail
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{uid}/refresh")
async def dm_refresh(uid: str, user=Depends(get_current_user_optional)):
    """
    Trigger background enrichment job (non-blocking).
    Frontend polls for updated details.
    """
    from backend.app.workers.decision_maker_tasks import dm_enrich_async

    user_id = getattr(user, "id", None) if user else None

    # enqueue async job
    dm_enrich_async.delay(uid, user_id)

    return {"queued": True, "uid": uid}

    from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db import get_async_db
from backend.app.services.decision_maker_service import (
    search_decision_makers,
    get_company_suggestions,
    enrich_single_dm,
    get_dm_detail
)
from backend.app.schemas.decision_maker import DecisionMakerResponse

router = APIRouter(prefix="/decision-maker", tags=["Decision Maker"])


# ----------------------------------------------------
# SEARCH (name, role, company)
# ----------------------------------------------------
@router.get("/search")
async def dm_search(
    q: str = Query("", description="keyword"),
    company: str | None = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=50),
    db: AsyncSession = Depends(get_async_db)
):
    result = await search_decision_makers(db, q=q, company=company, page=page, per_page=per_page)
    return result


# ----------------------------------------------------
# COMPANY AUTOCOMPLETE
# ----------------------------------------------------
@router.get("/company-suggest")
async def dm_company_suggest(
    q: str = Query(...),
    db: AsyncSession = Depends(get_async_db)
):
    suggestions = await get_company_suggestions(db, q)
    return suggestions


# ----------------------------------------------------
# SINGLE DM DETAIL
# ----------------------------------------------------
@router.get("/{dm_id}", response_model=DecisionMakerResponse)
async def dm_detail(dm_id: str, db: AsyncSession = Depends(get_async_db)):
    dm = await get_dm_detail(db, dm_id)
    if not dm:
        raise HTTPException(404, "Decision maker not found")
    return dm


# ----------------------------------------------------
# ENRICH A SINGLE PERSON (PDL + APOLLO)
# ----------------------------------------------------
@router.post("/enrich")
async def dm_enrich(payload: dict, db: AsyncSession = Depends(get_async_db)):
    dm_id = payload.get("id")
    if not dm_id:
        raise HTTPException(400, "Missing id")

    task_id = await enrich_single_dm(db, dm_id)
    return {"ok": True, "task_id": task_id}
