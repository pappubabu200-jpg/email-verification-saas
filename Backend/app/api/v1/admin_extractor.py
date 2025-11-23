# backend/app/api/v1/admin_extractor.py
from fastapi import APIRouter, Depends, HTTPException
from backend.app.utils.security import get_current_admin
from backend.app.db import SessionLocal
from backend.app.models.extractor_job import ExtractorJob
from backend.app.services.credits_service import capture_reservation_by_job, release_reservation_by_job

router = APIRouter(prefix="/api/v1/admin/extractor", tags=["admin-extractor"])

@router.get("/job/{job_id}")
def get_job(job_id: str, admin = Depends(get_current_admin)):
    db = SessionLocal()
    try:
        job = db.query(ExtractorJob).filter(ExtractorJob.job_id == job_id).first()
        if not job:
            raise HTTPException(status_code=404, detail="job_not_found")
        return {
            "job_id": job.job_id,
            "status": job.status,
            "input_path": job.input_path,
            "output_path": job.output_path,
            "processed": job.processed,
            "success": getattr(job, "success", None),
            "fail": getattr(job, "fail", None),
            "error_message": job.error_message
        }
    finally:
        db.close()

@router.post("/finalize/{job_id}")
def finalize_capture(job_id: str, processed_count: int = None, admin = Depends(get_current_admin)):
    """
    Manually finalize capture for a job. Use only if worker failed to capture automatically.
    """
    res = capture_reservation_by_job(job_id, processed_count=processed_count)
    return {"ok": True, "result": res}

@router.post("/release/{job_id}")
def release_all(job_id: str, admin = Depends(get_current_admin)):
    """
    Release remaining reservations for job_id (refund).
    """
    # find reservations and release them — reuse release_reservation_by_job if implemented, else simple loop
    db = SessionLocal()
    try:
        from backend.app.models.credit_reservation import CreditReservation
        rows = db.query(CreditReservation).filter(CreditReservation.job_id == job_id, CreditReservation.locked == True).all()
        released = []
        for r in rows:
            r.locked = False
            db.add(r)
            released.append(r.id)
        db.commit()
        return {"released": released}
    finally:
        db.close()
