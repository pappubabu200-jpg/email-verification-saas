# backend/app/api/v1/bulk_download.py
from fastapi import APIRouter, Depends, HTTPException
from backend.app.utils.security import get_current_user, get_current_admin
from backend.app.db import SessionLocal
import logging
import os

router = APIRouter(prefix="/api/v1/bulk-download", tags=["bulk-download"])
logger = logging.getLogger(__name__)

@router.get("/file/{job_id}")
def download_result(job_id: str, current_user = Depends(get_current_user)):
    """
    Return output_path for a bulk job if it belongs to the user.
    If MinIO/S3 path, optionally return pre-signed URL (if minio_client exists).
    """
    db = SessionLocal()
    try:
        BulkJob = __import__("backend.app.models.bulk_job", fromlist=["BulkJob"]).BulkJob
        job = db.query(BulkJob).filter(BulkJob.job_id == job_id).first()
        if not job:
            raise HTTPException(status_code=404, detail="job_not_found")
        if job.user_id != current_user.id and not getattr(current_user, "is_admin", False):
            raise HTTPException(status_code=403, detail="forbidden")

        if not job.output_path:
            raise HTTPException(status_code=404, detail="results_not_ready")

        # if s3/minio path -> generate presigned url if minio client available
        if str(job.output_path).startswith("s3://"):
            try:
                from backend.app.services.minio_client import client, MINIO_BUCKET, presign_get
                # output_path format: s3://{bucket}/path
                parts = str(job.output_path).replace("s3://", "").split("/", 1)
                if len(parts) == 2:
                    bucket, obj = parts[0], parts[1]
                else:
                    bucket, obj = MINIO_BUCKET, parts[0]

                url = presign_get(bucket, obj, expires=3600)
                return {"presigned_url": url}
            except Exception:
                logger.exception("presign failed - returning raw path")
                return {"path": job.output_path}

        # if local file -> return path (frontend/back-end should implement streaming)
        if os.path.exists(job.output_path):
            return {"path": job.output_path}
        return {"path": job.output_path}
    finally:
        db.close()

# Admin variant: download any job
@router.get("/admin/file/{job_id}", dependencies=[Depends(get_current_admin)])
def download_admin(job_id: str):
    db = SessionLocal()
    try:
        BulkJob = __import__("backend.app.models.bulk_job", fromlist=["BulkJob"]).BulkJob
        job = db.query(BulkJob).filter(BulkJob.job_id == job_id).first()
        if not job:
            raise HTTPException(status_code=404, detail="job_not_found")
        return {"path": job.output_path}
    finally:
        db.close()
