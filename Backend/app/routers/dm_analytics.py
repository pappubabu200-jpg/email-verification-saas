# backend/app/routers/dm_analytics.py

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from backend.app.db import get_async_db
from backend.app.models.decision_maker import DecisionMaker

router = APIRouter(prefix="/admin/dm", tags=["admin-dm"])


@router.get("/analytics")
async def dm_analytics(db: AsyncSession = Depends(get_async_db)):
    """
    Decision Maker Analytics:
    - total count
    - verified %
    - by department
    - by seniority
    - by title
    - by country/state (if available)
    """
    # -------- TOTAL COUNT --------
    total_q = await db.execute(select(func.count()).select_from(DecisionMaker))
    total = total_q.scalar() or 0

    # -------- VERIFIED COUNT --------
    verified_q = await db.execute(
        select(func.count()).where(DecisionMaker.verified == True)
    )
    verified = verified_q.scalar() or 0

    verified_pct = round((verified / total) * 100, 2) if total else 0

    # -------- BY DEPARTMENT --------
    dept_q = await db.execute(
        select(DecisionMaker.department, func.count())
        .group_by(DecisionMaker.department)
    )
    by_department = [{"department": d or "Unknown", "count": c} for d, c in dept_q.all()]

    # -------- BY SENIORITY --------
    seniority_q = await db.execute(
        select(DecisionMaker.seniority, func.count())
        .group_by(DecisionMaker.seniority)
    )
    by_seniority = [{"seniority": s or "Unknown", "count": c} for s, c in seniority_q.all()]

    # -------- BY TITLE --------
    title_q = await db.execute(
        select(DecisionMaker.title, func.count())
        .group_by(DecisionMaker.title)
        .order_by(func.count().desc())
    )
    by_title = [{"title": t or "Unknown", "count": c} for t, c in title_q.all()]

    # -------- BY LOCATION --------
    loc_q = await db.execute(
        select(DecisionMaker.location, func.count())
        .group_by(DecisionMaker.location)
    )
    by_location = [{"location": l or "Unknown", "count": c} for l, c in loc_q.all()]

    return {
        "total": total,
        "verified_pct": verified_pct,
        "by_department": by_department,
        "by_seniority": by_seniority,
        "by_title": by_title,
        "by_location": by_location,
    }
