# backend/app/api/v1/bulk.py
import os
import io
import uuid
import csv
import zipfile
import logging
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional, List

from fastapi import APIRouter, Request, Depends, UploadFile, File, HTTPException
from backend.app.db import SessionLocal
from backend.app.models.bulk_job import BulkJob
from backend.app.services.pricing_service import get_cost_for_key
from backend.app.services.credits_service import reserve_and_deduct, get_user_balance
from backend.app.workers.bulk_tasks import process_bulk_task
from backend.app.utils.security import get_current_user, get_current_admin
from backend.app.config import settings
from backend.app.services.minio_client import put_bytes, ensure_bucket, MINIO_BUCKET
from decimal import Decimal

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/bulk", tags=["bulk"])

# configure: how many seconds before reservation auto-expiry if you use reservations elsewhere
INPUT_PREFIX = getattr(settings, "BULK_INPUT_PREFIX", "inputs")
OUTPUT_PREFIX = getattr(settings, "BULK_OUTPUT_PREFIX", "outputs")

def _dec(x) -> Decimal:
    return Decimal(str(x)).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)

def _extract_emails_from_zip_bytes(content: bytes) -> List[str]:
    emails: List[str] = []
    z = zipfile.ZipFile(io.BytesIO(content))
    for name in z.namelist():
        if name.endswith("/") or name.startswith("__MACOSX"):
            continue
        if name.lower().endswith(".csv"):
            raw = z.read(name).decode("utf-8", errors="ignore")
            reader = csv.reader(io.StringIO(raw))
            for row in reader:
                for col in row:
                    v = col.strip()
                    if v and "@" in v:
                        emails.append(v)
                        break
        elif name.lower().endswith(".txt"):
            txt = z.read(name).decode("utf-8", errors="ignore")
            for line in txt.splitlines():
                s = line.strip()
                if s and "@" in s:
                    emails.append(s)
    return emails

def _extract_emails_from_csv_text(text: str) -> List[str]:
    emails: List[str] = []
    reader = csv.reader(io.StringIO(text))
    for row in reader:
        for col in row:
            v = col.strip()
            if v and "@" in v:
                emails.append(v)
                break
    return emails

# ---- submit job endpoint ----
@router.post("/submit")
async def submit_bulk(
    file: UploadFile = File(...),
    webhook_url: Optional[str] = None,
    request: Optional[Request] = None,
    team_id: Optional[int] = None,  # optional override from frontend
    current_user = Depends(get_current_user),
):
    user = current_user
    if not user:
        raise HTTPException(status_code=401, detail="auth_required")

    # decide team context (explicit override takes precedence)
    chosen_team = team_id or getattr(request.state, "team_id", None)

    # read file content
    content = await file.read()
    filename = (file.filename or f"upload-{uuid.uuid4().hex}").lower()

    # SAVE to MINIO
    ensure_bucket()
    object_name = f"{INPUT_PREFIX}/{user.id}-{uuid.uuid4().hex[:12]}-{filename}"
    try:
        input_path = put_bytes(object_name, content, content_type=file.content_type or "application/octet-stream")
    except Exception as e:
        logger.exception("minio save failed: %s", e)
        raise HTTPException(status_code=500, detail="save_input_failed")

    # QUICK COUNT / PARSE of emails
    emails = []
    try:
        _, ext = os.path.splitext(filename)
        ext = ext.lower()
        if ext == ".zip":
            emails = _extract_emails_from_zip_bytes(content)
        elif ext in (".csv", ".txt"):
            raw = content.decode("utf-8", errors="ignore")
            emails = _extract_emails_from_csv_text(raw)
        else:
            raw = content.decode("utf-8", errors="ignore")
            for line in raw.splitlines():
                s = line.strip()
                if s and "@" in s:
                    emails.append(s)
    except Exception as e:
        logger.exception("count parse failed: %s", e)
        raise HTTPException(status_code=400, detail="parse_failed")

    # dedupe + normalize
    unique_emails = list(dict.fromkeys([e.lower().strip() for e in emails if "@" in e]))
    total = len(unique_emails)
    if total == 0:
        raise HTTPException(status_code=400, detail="no_valid_emails")

    # Pricing & reservation — pass chosen_team into reserve_and_deduct
    per_cost = _dec(get_cost_for_key("verify.bulk_per_email") or 0)
    estimated_cost = (per_cost * Decimal(total)).quantize(Decimal("0.000001"))

    # Reserve credits up-front
    try:
        reserve_tx = reserve_and_deduct(
            user.id,
            estimated_cost,
            reference=f"bulk-reserve:{uuid.uuid4().hex[:8]}",
            team_id=chosen_team,
        )
    except HTTPException as e:
        raise e
    except Exception as e:
        logger.exception("reserve failed: %s", e)
        raise HTTPException(status_code=500, detail="reserve_failed")

    # create DB job with team_id recorded if model supports it
    db = SessionLocal()
    job_id = f"bulk-{uuid.uuid4().hex[:12]}"
    try:
        job = BulkJob(
            user_id = user.id,
            job_id = job_id,
            status = "queued",
            input_path = input_path,
            total = total,
            webhook_url = webhook_url
        )
        try:
            setattr(job, "team_id", chosen_team)
        except Exception:
            pass

        db.add(job)
        db.commit()
        db.refresh(job)
    except Exception as e:
        logger.exception("failed to create job row: %s", e)
        # attempt to refund reservation (best-effort)
        try:
            from backend.app.services.credits_service import add_credits
            add_credits(user.id, estimated_cost, reference=f"{job_id}:refund_on_create_fail")
        except Exception:
            logger.exception("refund after job create fail also failed")
        raise HTTPException(status_code=500, detail="job_create_failed")
    finally:
        db.close()

    # enqueue Celery task with estimated_cost
    try:
        process_bulk_task.delay(job_id, float(estimated_cost))
    except Exception:
        logger.exception("enqueue failed, job created")

    return {
        "job_id": job_id,
        "total": total,
        "estimated_cost": float(estimated_cost),
        "reserve_tx": reserve_tx,
    }


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
            "error_message": job.error_message,
            "team_id": getattr(job, "team_id", None),
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
        return {"output_path": job.output_path}
    finally:
        db.close()


@router.get("/my-jobs")
def list_my_jobs(page: int = 1, per_page: int = 20, current_user = Depends(get_current_user)):
    db = SessionLocal()
    try:
        q = db.query(BulkJob).filter(BulkJob.user_id == current_user.id).order_by(BulkJob.created_at.desc())
        total = q.count()
        rows = q.limit(per_page).offset((page-1)*per_page).all()
        items = []
        for r in rows:
            items.append({
                "job_id": r.job_id,
                "status": r.status,
                "total": r.total,
                "processed": r.processed,
                "valid": r.valid,
                "invalid": r.invalid,
                "created_at": str(r.created_at),
                "output_path": r.output_path,
                "team_id": getattr(r, "team_id", None),
            })
        return {
            "page": page,
            "per_page": per_page,
            "total": total,
            "items": items,
        }
    finally:
        db.close()
