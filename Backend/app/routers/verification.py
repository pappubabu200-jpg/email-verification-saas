# backend/app/routers/verification.py

from fastapi import (
    APIRouter, Depends, HTTPException, UploadFile,
    File, status
)
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db import async_session
from backend.app.services.auth_service import get_current_user

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
    Uses:
      - suppression list
      - domain cache
      - existing results cache
      - TODO: SMTP/MX verification engine
    """

    email = email.lower().strip()

    # ---------------------------------------
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

    # ---------------------------------------
    # 2. Domain cache lookup
    domain_repo = DomainCacheRepository(db)
    domain = email.split("@")[1]
    cached_domain = await domain_repo.get_by_domain(domain)
    domain_status = cached_domain.provider if cached_domain else None

    # ---------------------------------------
    # 3. Check if user verified this email already (cache)
    ver_repo = VerificationResultRepository(db)
    existing = await ver_repo.get_by_email(email)
    if existing:
        return VerificationResultResponse.from_orm(existing)

    # ---------------------------------------
    # 4. TODO: Real SMTP verification engine goes here
    # For now, mark as "valid" (placeholder)
    status_result = "valid"
    reason = None
    score = 0.95

    # ---------------------------------------
    # 5. Save result
    result = await ver_repo.create({
        "user_id": current_user.id,
        "email": email,
        "status": status_result,
        "reason": reason,
        "domain": domain,
        "score": score
    })

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
    """
    Creates bulk verification job.
    Saves file temporarily (memory/local) — you can replace with S3.
    """

    if not file.filename.endswith(".csv"):
        raise HTTPException(400, "Only CSV files allowed.")

    # Read CSV content
    content = await file.read()
    text = content.decode("utf-8")
    reader = csv.reader(io.StringIO(text))
    emails = [row[0].strip().lower() for row in reader if row]

    if len(emails) == 0:
        raise HTTPException(400, "CSV is empty.")

    # Reserve credits
    credit_repo = CreditReservationRepository(db)
    job_id = str(uuid.uuid4())

    await credit_repo.create({
        "user_id": current_user.id,
        "amount": len(emails),
        "job_id": job_id,
        "locked": True,
    })

    # Create bulk job
    bulk_repo = BulkJobRepository(db)
    job = await bulk_repo.create({
        "user_id": current_user.id,
        "job_id": job_id,
        "status": "queued",
        "total": len(emails),
        "processed": 0,
        "valid": 0,
        "invalid": 0,
        "input_path": None,   # You can store in S3 later
        "output_path": None,
    })

    return {
        "job_id": job_id,
        "total_emails": len(emails),
        "status": "queued"
    }


# ---------------------------------------------------------
# BULK JOB STATUS
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


# ---------------------------------------------------------
# BULK RESULTS (placeholder)
# ---------------------------------------------------------
@router.get("/bulk/results/{job_id}")
async def bulk_job_results(
    job_id: str,
    current_user = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Returns bulk job results.
    TODO: when you implement worker → set output_path and file download.
    """
    bulk_repo = BulkJobRepository(db)
    job = await bulk_repo.get_by_job_id(job_id)

    if not job or job.user_id != current_user.id:
        raise HTTPException(404, "Job not found.")

    if not job.output_path:
        return {"status": job.status, "message": "Results not ready yet"}

    return {"download_url": job.output_path}


# ---------------------------------------------------------
# CANCEL BULK JOB
# ---------------------------------------------------------
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
