
# backend/app/routers/dm_autodiscovery.py
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from typing import Optional
from backend.app.celery_app import celery_app
from backend.app.db import SessionLocal

router = APIRouter(prefix="/dm", tags=["decision_maker"])


class AutoDiscoveryRequest(BaseModel):
    domain: Optional[str] = Field(None, description="Company domain (example.com)")
    company_name: Optional[str] = Field(None, description="Company name")
    max_results: int = Field(50, ge=1, le=500, description="How many results to fetch")
    user_id: Optional[int] = Field(None, description="Optional requesting user id for billing / ws")


class AutoDiscoveryResponse(BaseModel):
    job_id: str
    status: str


@router.post("/discover", response_model=AutoDiscoveryResponse, status_code=status.HTTP_202_ACCEPTED)
async def start_autodiscovery(payload: AutoDiscoveryRequest):
    if not payload.domain and not payload.company_name:
        raise HTTPException(status_code=400, detail="domain or company_name required")

    # create a lightweight job id (UUID)
    import uuid
    job_id = str(uuid.uuid4())

    # enqueue celery task - worker will perform discovery and save results
    try:
        celery_app.send_task(
            "workers.decision_maker_tasks.autodiscover_job",
            args=[job_id, payload.domain, payload.company_name, payload.max_results, payload.user_id],
            kwargs={},
            queue="default",
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to enqueue discovery: {e}")

    return {"job_id": job_id, "status": "queued"}
