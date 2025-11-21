# backend/app/api/v1/bulk.py
import os, io, uuid, csv, zipfile, logging
from fastapi import APIRouter, Request, Depends, UploadFile, File, HTTPException
from backend.app.db import SessionLocal
from backend.app.models.bulk_job import BulkJob
from backend.app.services.pricing_service import get_cost_for_key
from backend.app.services.credits_service import reserve_and_deduct, get_user_balance
from backend.app.workers.bulk_tasks import process_bulk_task
from backend.app.utils.security import get_current_user, get_current_admin
from backend.app.config import settings
from decimal import Decimal, ROUND_HALF_UP

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/bulk", tags=["bulk"])

INPUT_FOLDER = getattr(settings, "BULK_INPUT_FOLDER", "/tmp/bulk_inputs")
os.makedirs(INPUT_FOLDER, exist_ok=True)

def _dec(x) -> Decimal:
    return Decimal(str(x)).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)

# ---- submit job endpoint ----
@router.post("/submit")
async def submit_bulk(file: UploadFile = File(...), webhook_url: str = None, request: Request = None, current_user = Depends(get_current_user)):
    user = current_user
    if not user:
        raise HTTPException(status_code=401, detail="auth_required")

    content = await file.read()
    filename = (file.filename or f"upload-{uuid.uuid4().hex}").lower()
    # Save input to disk
    fname = f"{user.id}-{uuid.uuid4().hex[:12]}-{filename}"
    input_path = os.path.join(INPUT_FOLDER, fname)
    with open(input_path, "wb") as fh:
        fh.write(content)

    # Count emails quickly (simple CSV/text parse)
    emails = []
    try:
        _, ext = os.path.splitext(filename)
        if ext == ".zip":
            z = zipfile.ZipFile(io.BytesIO(content))
            for name in z.namelist():
                if name.endswith("/") or name.startswith("__MACOSX"):
                    continue
                if name.lower().endswith((".csv", ".txt")):
                    raw = z.read(name).decode("utf-8", errors="ignore")
                    # simple line parse
                    for line in raw.splitlines():
                        s = line.strip()
                        if s and "@" in s:
                            emails.append(s)
        elif ext in (".csv", ".txt"):
            raw = content.decode("utf-8", errors="ignore")
            for row in csv.reader(io.StringIO(raw)):
                for col in row:
                    v = col.strip()
                    if v and "@" in v:
                        emails.append(v)
                        break
        else:
            # fallback: line parser
            raw = content.decode("utf-8", errors="ignore")
            for line in raw.splitlines():
                s = line.strip()
                if s and "@" in s:
                    emails.append(s)
    except Exception as e:
        logger.exception("count parse failed: %s", e)
        raise HTTPException(status_code=400, detail="parse_failed")

    unique_emails = list(dict.fromkeys([e.lower() for e in emails]))
    total = len(unique_emails)
    if total == 0:
        raise HTTPException(status_code=400, detail="no_valid_emails")

    # Pricing & reservation
    per_cost = _dec(get_cost_for_key("verify.bulk_per_email") or 0)
    estimated_cost = (per_cost * Decimal(total)).quantize(Decimal("0.000001"))

    # Reserve credits up-front
    try:
        reserve_tx = reserve_and_deduct(user.id, estimated_cost, reference=f"bulk-reserve:{uuid.uuid4().hex[:8]}")
    except HTTPException as e:
        raise e

    # create DB job
    db = SessionLocal()
    try:
        job_id = f"bulk-{uuid.uuid4().hex[:12]}"
        job = BulkJob(
            user_id = user.id,
            job_id = job_id,
            status = "queued",
            input_path = input_path,
            total = total,
            webhook_url = webhook_url
        )
        db.add(job); db.commit(); db.refresh(job)
    finally:
        db.close()

    # enqueue Celery task with estimated_cost passed
    try:
        process_bulk_task.delay(job_id, float(estimated_cost))
    except Exception:
        logger.exception("enqueue failed, but job created")
        # we keep job queued; worker restart will pick it (or you can schedule)
    return {"job_id": job_id, "total": total, "estimated_cost": float(estimated_cost), "reserve_tx": reserve_tx}

# ---- admin endpoints ----
@router.get("/status/{job_id}")
def job_status(job_id: str, admin = Depends(get_current_admin)):
    db = SessionLocal()
    try:
        job = db.query(BulkJob).filter(BulkJob.job_id == job_id).first()
        if not job:
            raise HTTPException(status_code=404, detail="job_not_found")
        return {
            "job_id": job.job_id,
            "status": job.status,
            "total": job.total,
            "processed": job.processed,
            "valid": job.valid,
            "invalid": job.invalid,
            "input_path": job.input_path,
            "output_path": job.output_path,
            "error_message": job.error_message
        }
    finally:
        db.close()

@router.get("/download/{job_id}")
def download_results(job_id: str, admin = Depends(get_current_admin)):
    db = SessionLocal()
    try:
        job = db.query(BulkJob).filter(BulkJob.job_id == job_id).first()
        if not job or not job.output_path:
            raise HTTPException(status_code=404, detail="results_not_ready")
        # return path so frontend can download from file server (or implement streaming endpoint)
        return {"output_path": job.output_path}
    finally:
        db.close()


# inside the existing bulk router in backend/app/api/v1/bulk.py

@router.get("/my-jobs")
def list_my_jobs(page: int = 1, per_page: int = 20, current_user = Depends(get_current_user)):
    db = SessionLocal()
    try:
        q = db.query(BulkJob).filter(BulkJob.user_id == current_user.id).order_by(BulkJob.created_at.desc())
        total = q.count()
        rows = q.limit(per_page).offset((page-1)*per_page).all()
        return {
            "page": page,
            "per_page": per_page,
            "total": total,
            "items": [
                {
                    "job_id": r.job_id,
                    "status": r.status,
                    "total": r.total,
                    "processed": r.processed,
                    "valid": r.valid,
                    "invalid": r.invalid,
                    "created_at": str(r.created_at),
                    "output_path": r.output_path
                } for r in rows
            ]
        }
    finally:
        db.close()



