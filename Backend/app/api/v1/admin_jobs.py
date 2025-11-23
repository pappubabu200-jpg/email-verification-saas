# backend/app/api/v1/admin_jobs.py
from fastapi import APIRouter, Depends, HTTPException
from backend.app.utils.security import get_current_admin
from backend.app.db import SessionLocal
from backend.app.models.bulk_job import BulkJob
import json

router = APIRouter(prefix="/api/v1/admin/jobs", tags=["admin-jobs"])

@router.get("/reconcile/{job_id}")
def reconcile_job(job_id: str, admin = Depends(get_current_admin)):
    db = SessionLocal()
    try:
        job = db.query(BulkJob).filter(BulkJob.job_id == job_id).first()
        if not job:
            raise HTTPException(status_code=404, detail="job_not_found")

        result = {
            "job_id": job.job_id,
            "status": job.status,
            "total": job.total,
            "processed": job.processed,
            "valid": job.valid,
            "invalid": job.invalid,
            "output_path": job.output_path,
            "error_message": job.error_message,
            "has_output": job.output_path is not None
        }

        return result
    finally:
        db.close()
