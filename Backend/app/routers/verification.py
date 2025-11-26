# backend/app/routers/verification.py

from fastapi import (
    APIRouter, Depends, HTTPException, UploadFile,
    File, status
)
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db import async_session
from backend.app.services.auth_service import get_current_user
from backend.app.services.webhook_service import trigger_webhook  # ← ADDED

from backend.app.repositories.verification_result_repository import VerificationResultRepository
from backend.app.repositories.bulk_job_repository import BulkJobRepository
from backend.app.repositories.domain_cache_repository import DomainCacheRepository
from backend.app.repositories.suppression_repository import SuppressionRepository
from backend.app.repositories.credit_reservation_repository import CreditReservationRepository

from backend.app.schemas.verification_result import VerificationResultResponse
from backend.app.schemas.bulk_job import BulkJobResponse

import uuid
import csv
import io

router = APIRouter(prefix="/verify", tags=["verification"])


# ---------------------------------------
# DB Dependency
# ---------------------------------------
async def get_db():
    async with async_session() as session:
        yield session


# ---------------------------------------------------------
# SINGLE EMAIL VERIFICATION  /verify/email
# ---------------------------------------------------------
@router.get("/email", response_model=VerificationResultResponse)
async def verify_single_email(
    email: str,
    current_user = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Real-time single email verification (ZeroBounce style).
    Now with webhook on completion!
    """

    email = email.lower().strip()

    # 1. Check suppression list
    suppression_repo = SuppressionRepository(db)
    if await suppression_repo.is_suppressed(email):
        return VerificationResultResponse(
            id=0,
            user_id=current_user.id,
            email=email,
            status="suppressed",
            reason="email-in-suppression-list",
            domain=email.split("@")[1],
            score=0
        )

    # 2. Domain cache lookup
    domain_repo = DomainCacheRepository(db)
    domain = email.split("@")[1]
    cached_domain = await domain_repo.get_by_domain(domain)
    domain_status = cached_domain.provider if cached_domain else None

    # 3. Check cache
    ver_repo = VerificationResultRepository(db)
    existing = await ver_repo.get_by_email(email)
    if existing:
        return VerificationResultResponse.from_orm(existing)

    # 4. TODO: Real verification engine here
    status_result = "valid"
    reason = None
    score = 0.95

    # 5. Save result
    result = await ver_repo.create({
        "user_id": current_user.id,
        "email": email,
        "status": status_result,
        "reason": reason,
        "domain": domain,
        "score": score
    })

    # WEBHOOK: Fire and forget — never breaks the API response
    try:
        await trigger_webhook(
            "verification.completed",
            {
                "email": email,
                "status": status_result,
                "score": score,
                "reason": reason,
                "domain": domain,
                "user_id": current_user.id,
                "team_id": getattr(current_user, "team_id", None) or current_user.id,
                "credits_used": 1
            },
            team_id=getattr(current_user, "team_id", None) or current_user.id
        )
    except Exception as e:
        print(f"Webhook failed (non-blocking): {e}")

    return VerificationResultResponse.from_orm(result)


# ---------------------------------------------------------
# Alias: /verify/single
# ---------------------------------------------------------
@router.get("/single", response_model=VerificationResultResponse)
async def verify_single_alias(
    email: str,
    current_user = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    return await verify_single_email(email, current_user, db)


# ---------------------------------------------------------
# BULK VERIFICATION — INIT JOB
# ---------------------------------------------------------
@router.post("/bulk/init", response_model=dict)
async def init_bulk_job(
    file: UploadFile = File(...),
    current_user = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    if not file.filename.endswith(".csv"):
        raise HTTPException(400, "Only CSV files allowed.")

    content = await file.read()
    text = content.decode("utf-8")
    reader = csv.reader(io.StringIO(text))
    emails = [row[0].strip().lower() for row in reader if row]

    if len(emails) == 0:
        raise HTTPException(400, "CSV is empty.")

    credit_repo = CreditReservationRepository(db)
    job_id = str(uuid.uuid4())

    await credit_repo.create({
        "user_id": current_user.id,
        "amount": len(emails),
        "job_id": job_id,
        "locked": True,
    })

    bulk_repo = BulkJobRepository(db)
    job = await bulk_repo.create({
        "user_id": current_user.id,
        "job_id": job_id,
        "status": "queued",
        "total": len(emails),
        "processed": 0,
        "valid": 0,
        "invalid": 0,
        "input_path": None,
        "output_path": None,
    })

    return {
        "job_id": job_id,
        "total_emails": len(emails),
        "status": "queued"
    }


# ---------------------------------------------------------
# BULK JOB STATUS + RESULTS + CANCEL (unchanged)
# ---------------------------------------------------------
@router.get("/bulk/status/{job_id}", response_model=BulkJobResponse)
async def bulk_job_status(
    job_id: str,
    current_user = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    bulk_repo = BulkJobRepository(db)
    job = await bulk_repo.get_by_job_id(job_id)
    if not job or job.user_id != current_user.id:
        raise HTTPException(404, "Job not found.")
    return BulkJobResponse.from_orm(job)


@router.get("/bulk/results/{job_id}")
async def bulk_job_results(
    job_id: str,
    current_user = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    bulk_repo = BulkJobRepository(db)
    job = await bulk_repo.get_by_job_id(job_id)
    if not job or job.user_id != current_user.id:
        raise HTTPException(404, "Job not found.")
    if not job.output_path:
        return {"status": job.status, "message": "Results not ready yet"}
    return {"download_url": job.output_path}


@router.post("/bulk/cancel/{job_id}")
async def bulk_job_cancel(
    job_id: str,
    current_user = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    bulk_repo = BulkJobRepository(db)
    job = await bulk_repo.get_by_job_id(job_id)
    if not job or job.user_id != current_user.id:
        raise HTTPException(404, "Job not found.")
    if job.status in ("completed", "failed"):
        raise HTTPException(400, "Cannot cancel a finished job.")
    await bulk_repo.update(job, {"status": "cancelled"})
    return {"cancelled": True, "job_id": job_id}

