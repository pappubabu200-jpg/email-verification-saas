
# backend/app/routers/decision_maker_results.py

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db import get_async_db
from backend.app.services.decision_maker_results_service import (
    get_results_for_job,
    export_results_csv,
)

router = APIRouter(prefix="/decision-maker/results", tags=["Decision Maker Results"])


@router.get("/{job_id}")
async def get_results(job_id: str, db: AsyncSession = Depends(get_async_db)):
    """
    Return final decision maker results for a discovery job.
    """
    data = await get_results_for_job(db, job_id)
    if not data:
        raise HTTPException(status_code=404, detail="Result not found")
    return data


@router.get("/{job_id}/export")
async def export_csv(job_id: str, db: AsyncSession = Depends(get_async_db)):
    """
    Download CSV of final DM results.
    """
    csv_bytes = await export_results_csv(db, job_id)
    if not csv_bytes:
        raise HTTPException(status_code=404, detail="Result not found")

    return Response(
        content=csv_bytes,
        media_type="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename=dm_results_{job_id}.csv"
        }
    )
