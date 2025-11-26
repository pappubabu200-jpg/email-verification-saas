# backend/app/routers/bulk_jobs.py

import uuid
import csv
import io
import os

from fastapi import (
    APIRouter, Depends, HTTPException,
    UploadFile, File, status
)
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db import async_session
from backend.app.services.auth_service import get_current_user

from backend.app.repositories.bulk_job_repository import BulkJobRepository
from backend.app.repositories.credit_reservation_repository import CreditReservationRepository
from backend.app.repositories.verification_result_repository import VerificationResultRepository
from backend.app.schemas.bulk_job import BulkJobResponse

router = APIRouter(prefix="/bulk", tags=["bulk-jobs"])


# -------------------------------------------------------
# DB Dependency
# -------------------------------------------------------
async def get_db():
    async with async_session() as session:
        yield session


# -------------------------------------------------------
# POST /bulk/upload  → Save CSV File (Local or S3)
# -------------------------------------------------------
@router.post("/upload")
async def upload_bulk_file(
    file: UploadFile = File(...),
    current_user = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Upload CSV & return upload_id.
    You can later move to S3/MinIO easily.
    """

    if not file.filename.endswith(".csv"):
        raise HTTPException(400, "Only CSV files allowed.")

    content = await file.read()
    upload_id = str(uuid.uuid4())

    # Save to local storage (production → use S3)
    folder = "uploads"
    os.makedirs(folder, exist_ok=True)
    path = f"{folder}/{upload_id}.csv"

    with open(path, "wb") as f:
        f.write(content)

    return {
        "upload_id": upload_id,
        "filename": file.filename,
        "path": path
    }


# -------------------------------------------------------
# POST /bulk/create-job  → Create Bulk Job Entry
# -------------------------------------------------------
@router.post("/create-job", response_model=dict)
async def create_bulk_job(
    upload_id: str,
    current_user = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Creates database bulk job record.
    """

    # Validate upload_id is a UUID
    try:
        val = uuid.UUID(upload_id)
    except ValueError:
        raise HTTPException(400, "Invalid upload_id format. Must be a UUID.")

    uploads_folder = os.path.abspath("uploads")
    file_path = os.path.join(uploads_folder, f"{upload_id}.csv")
    norm_file_path = os.path.normpath(file_path)

    # Ensure file is within uploads folder
    if not norm_file_path.startswith(uploads_folder + os.sep):  # uploads_folder + os.sep to match only inside folder
        raise HTTPException(400, "Invalid upload_id path traversal detected.")

    if not os.path.exists(norm_file_path):
        raise HTTPException(404, "Uploaded file not found.")

    # Count emails
    with open(norm_file_path, "r") as f:
        reader = csv.reader(f)
        emails = [r[0].strip().lower() for r in reader if r]

    total = len(emails)
    if total == 0:
        raise HTTPException(400, "CSV is empty.")

    # Reserve credits
    credit_repo = CreditReservationRepository(db)
    job_id = str(uuid.uuid4())

    await credit_repo.create({
        "user_id": current_user.id,
        "amount": total,
        "job_id": job_id,
    })

    # Create job
    bulk_repo = BulkJobRepository(db)
    job = await bulk_repo.create({
        "user_id": current_user.id,
        "job_id": job_id,
        "status": "queued",
        "input_path": file_path,
        "output_path": None,
        "total": total,
        "processed": 0,
        "valid": 0,
        "invalid": 0,
    })

    return {
        "job_id": job_id,
        "total": total,
        "status": "queued"
    }


# -------------------------------------------------------
# POST /bulk/queue/{job_id}  → Send Job to Worker
# -------------------------------------------------------
@router.post("/queue/{job_id}")
async def queue_bulk_job(
    job_id: str,
    current_user = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Signals a worker (Celery/RQ) to process the file.
    In production, push job ID into Redis queue.
    """

    bulk_repo = BulkJobRepository(db)
    job = await bulk_repo.get_by_job_id(job_id)

    if not job or job.user_id != current_user.id:
        raise HTTPException(404, "Job not found.")

    if job.status not in ("queued", "failed"):
        raise HTTPException(400, "Job already processing or completed.")

    # In real deployment: enqueue background worker here
    # (Celery, RQ, Dramatiq, etc.)

    await bulk_repo.update(job, {"status": "processing"})

    return {"queued": True, "job_id": job_id, "status": "processing"}


# -------------------------------------------------------
# GET /bulk/status/{job_id}
# -------------------------------------------------------
@router.get("/status/{job_id}", response_model=BulkJobResponse)
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


# -------------------------------------------------------
# GET /bulk/download/{job_id} → Download Results
# -------------------------------------------------------
@router.get("/download/{job_id}")
async def bulk_job_download(
    job_id: str,
    current_user = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    bulk_repo = BulkJobRepository(db)
    job = await bulk_repo.get_by_job_id(job_id)

    if not job or job.user_id != current_user.id:
        raise HTTPException(404, "Job not found.")

    if not job.output_path:
        raise HTTPException(400, "Results not ready.")

    return FileResponse(
        path=job.output_path,
        filename=f"{job_id}_results.csv",
        media_type="text/csv"
    )


# -------------------------------------------------------
# POST /bulk/cancel/{job_id}
# -------------------------------------------------------
@router.post("/cancel/{job_id}")
async def cancel_bulk_job(
    job_id: str,
    current_user = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    bulk_repo = BulkJobRepository(db)
    job = await bulk_repo.get_by_job_id(job_id)

    if not job or job.user_id != current_user.id:
        raise HTTPException(404, "Job not found.")

    if job.status in ("completed", "failed"):
        raise HTTPException(400, "Job already finished.")

    await bulk_repo.update(job, {"status": "cancelled"})
    return {"cancelled": True, "job_id": job_id}


# -------------------------------------------------------
# DELETE /bulk/{job_id}
# -------------------------------------------------------
@router.delete("/{job_id}")
async def delete_bulk_job(
    job_id: str,
    current_user = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    bulk_repo = BulkJobRepository(db)
    job = await bulk_repo.get_by_job_id(job_id)

    if not job or job.user_id != current_user.id:
        raise HTTPException(404, "Job not found.")

    await bulk_repo.delete(job)
    return {"deleted": True}
