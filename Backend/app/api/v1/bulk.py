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
from backend.app.services.credits_service import reserve_and_deduct, get_user_balance, add_credits
from backend.app.workers.bulk_tasks import process_bulk_task
from backend.app.utils.security import get_current_user, get_current_admin
from backend.app.config import settings

# MinIO client helper
from backend.app.services.minio_client import client as minio_client, MINIO_BUCKET, ensure_bucket

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/bulk", tags=["bulk"])

INPUT_FOLDER = getattr(settings, "BULK_INPUT_FOLDER", "/tmp/bulk_inputs")
os.makedirs(INPUT_FOLDER, exist_ok=True)

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
    """
    Submit a bulk verification job. Saves input to MinIO (preferred) or disk.
    Reserves credits (team-first if team_id provided), creates BulkJob row with
    job_id and estimated_cost and leaves processing to Celery worker.
    """
    user = current_user
    if not user:
        raise HTTPException(status_code=401, detail="auth_required")

    chosen_team = team_id or getattr(request.state, "team_id", None)

    # validate team membership (best-effort)
    if chosen_team:
        try:
            from backend.app.services.team_service import is_user_member_of_team
            if not is_user_member_of_team(user.id, chosen_team):
                raise HTTPException(status_code=403, detail="not_team_member")
        except HTTPException:
            raise
        except Exception:
            raise HTTPException(status_code=403, detail="not_team_member")

    # read file content
    content = await file.read()
    filename = (file.filename or f"upload-{uuid.uuid4().hex}").lower()

    # Save to MinIO (preferred)
    try:
        ensure_bucket()
        object_name = f"inputs/{user.id}-{uuid.uuid4().hex[:12]}-{filename}"
        minio_client.put_object(
            MINIO_BUCKET,
            object_name,
            io.BytesIO(content),
            length=len(content),
            content_type=file.content_type or "application/octet-stream"
        )
        input_path = f"s3://{MINIO_BUCKET}/{object_name}"
    except Exception as e:
        logger.exception("minio save failed, fallback to disk: %s", e)
        # fallback to disk
        fname = f"{user.id}-{uuid.uuid4().hex[:12]}-{filename}"
        input_path = os.path.join(INPUT_FOLDER, fname)
        try:
            with open(input_path, "wb") as fh:
                fh.write(content)
        except Exception:
            logger.exception("disk save also failed")
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

    # Reserve credits up-front (team-first if chosen_team provided)
    try:
        reserve_tx = reserve_and_deduct(
            user.id,
            estimated_cost,
            reference=f"bulk-reserve:{uuid.uuid4().hex[:8]}",
            team_id=chosen_team,
            job_id=None,  # will attach job_id after create
        )
    except HTTPException as e:
        raise e
    except Exception as e:
        logger.exception("reserve failed: %s", e)
        raise HTTPException(status_code=500, detail="reserve_failed")

    # create DB job with team_id recorded
    db = SessionLocal()
    job_id = f"bulk-{uuid.uuid4().hex[:12]}"
    try:
        job = BulkJob(
            user_id = user.id,
            job_id = job_id,
            status = "queued",
            input_path = input_path,
            total = total,
            webhook_url = webhook_url,
            estimated_cost = float(estimated_cost)
        )
        # attach team_id if BulkJob model has attribute
        try:
            setattr(job, "team_id", chosen_team)
        except Exception:
            pass

        db.add(job)
        db.commit()
        db.refresh(job)

        # Link reservation(s) to job_id if reservation system used job_id field
        try:
            from backend.app.models.credit_reservation import CreditReservation
            res_rows = db.query(CreditReservation).filter(CreditReservation.user_id==user.id, CreditReservation.locked==True, CreditReservation.job_id==None).all()
            for r in res_rows:
                r.job_id = job_id
                db.add(r)
            db.commit()
        except Exception:
            # not critical
            pass

    except Exception as e:
        logger.exception("failed to create job row: %s", e)
        # attempt to refund reservation (best-effort)
        try:
            add_credits(user.id, estimated_cost, reference=f"{job_id}:refund_on_create_fail")
        except Exception:
            logger.exception("refund after job create fail also failed")
        raise HTTPException(status_code=500, detail="job_create_failed")
    finally:
        db.close()

    # enqueue Celery task with estimated_cost (worker will finalize and handle refunds)
    try:
        process_bulk_task.delay(job_id, float(estimated_cost))
    except Exception as e:
        logger.exception("enqueue failed, job created: %s", e)
        # keep job queued — worker may be restarted. We still return success to client.

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
            "estimated_cost": float(getattr(job, "estimated_cost", 0) or 0),
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


# ---- user endpoints ----
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



@router.get("/download-url/{job_id}")
def get_signed_download_url(job_id: str, current_user = Depends(get_current_user)):
    db = SessionLocal()
    try:
        job = db.query(BulkJob).filter(BulkJob.job_id == job_id).first()
        if not job:
            raise HTTPException(status_code=404, detail="job_not_found")

        if not job.output_path or not job.output_path.startswith("s3://"):
            raise HTTPException(status_code=400, detail="no_output_available")

        # Extract object path
        object_key = job.output_path.replace("s3://", "").split("/", 1)[1]

        from backend.app.services.minio_signed_url import generate_signed_url
        url = generate_signed_url(object_key, expiry_seconds=1800)

        return {"download_url": url}

    finally:
        db.close()
        
# backend/app/api/v1/bulk.py

import os, io, uuid, csv, zipfile, logging
from fastapi import APIRouter, Request, Depends, UploadFile, File, HTTPException
from decimal import Decimal, ROUND_HALF_UP

from backend.app.db import SessionLocal
from backend.app.models.bulk_job import BulkJob
from backend.app.services.pricing_service import get_cost_for_key
from backend.app.services.credits_service import reserve_and_deduct
from backend.app.services.team_service import is_user_member_of_team
from backend.app.workers.bulk_tasks import process_bulk_task
from backend.app.services.minio_client import client, MINIO_BUCKET
from backend.app.utils.security import get_current_user
from backend.app.config import settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/bulk", tags=["bulk"])

def _dec(x):
    return Decimal(str(x)).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)


# -------------------------
# SUBMIT BULK JOB
# -------------------------
@router.post("/submit")
async def submit_bulk(
    file: UploadFile = File(...),
    webhook_url: str = None,
    request: Request = None,
    team_id: int = None,
    current_user = Depends(get_current_user),
):
    """
    Team billing priority:
      1) If team_id provided → deduct from team pool (if admin or member)
      2) If insufficient → fall back to user credits
    """
    user = current_user
    if not user:
        raise HTTPException(status_code=401, detail="auth_required")

    # Determine chosen team (query & middleware combined)
    chosen_team = team_id or getattr(request.state, "team_id", None)

    # If team chosen, validate membership
    if chosen_team:
        if not is_user_member_of_team(user.id, chosen_team):
            raise HTTPException(status_code=403, detail="not_team_member")

    # Read file from user
    content = await file.read()
    filename = (file.filename or f"upload-{uuid.uuid4().hex}").lower()

    # ---------------------
    # SAVE TO MINIO
    # ---------------------
    object_name = f"inputs/{user.id}-{uuid.uuid4().hex[:10]}-{filename}"

    client.put_object(
        MINIO_BUCKET,
        object_name,
        io.BytesIO(content),
        length=len(content),
        content_type=file.content_type or "application/octet-stream",
    )

    input_path = f"s3://{MINIO_BUCKET}/{object_name}"

    # ---------------------
    # PARSE EMAILS
    # ---------------------
    emails = []

    try:
        if filename.endswith(".zip"):
            z = zipfile.ZipFile(io.BytesIO(content))
            for name in z.namelist():
                if name.lower().endswith(".csv"):
                    raw = z.read(name).decode("utf-8", errors="ignore")
                    for row in csv.reader(io.StringIO(raw)):
                        for col in row:
                            if "@" in col:
                                emails.append(col.strip())
                                break
                elif name.lower().endswith(".txt"):
                    for line in z.read(name).decode("utf-8", errors="ignore").splitlines():
                        if "@" in line:
                            emails.append(line.strip())

        elif filename.endswith(".csv"):
            raw = content.decode("utf-8", errors="ignore")
            for row in csv.reader(io.StringIO(raw)):
                for col in row:
                    if "@" in col:
                        emails.append(col.strip())
                        break
        else:
            # Fallback TXT
            raw = content.decode("utf-8", errors="ignore")
            for line in raw.splitlines():
                if "@" in line:
                    emails.append(line.strip())

    except Exception as e:
        logger.exception("parse_failed: %s", e)
        raise HTTPException(status_code=400, detail="parse_failed")

    # Clean & dedupe
    emails = [e.lower().strip() for e in emails if "@" in e]
    emails = list(dict.fromkeys(emails))

    total = len(emails)
    if total == 0:
        raise HTTPException(status_code=400, detail="no_valid_emails")

    # ---------------------
    # PRICING & RESERVATION
    # ---------------------
    per_cost = _dec(get_cost_for_key("verify.bulk_per_email"))
    estimated_cost = (per_cost * Decimal(total)).quantize(Decimal("0.000001"))

    job_id = f"bulk-{uuid.uuid4().hex[:12]}"

    # Reserve credits (team first if provided)
    reserve_tx = reserve_and_deduct(
        user.id,
        estimated_cost,
        reference=f"{job_id}:reserve",
        team_id=chosen_team,
        job_id=job_id,
    )

    # ---------------------
    # CREATE JOB IN DB
    # ---------------------
    db = SessionLocal()
    try:
        job = BulkJob(
            user_id=user.id,
            job_id=job_id,
            status="queued",
            total=total,
            input_path=input_path,
            webhook_url=webhook_url,
            team_id=chosen_team,
        )
        db.add(job)
        db.commit()
    finally:
        db.close()

    # ---------------------
    # ENQUEUE WORKER
    # ---------------------
    try:
        process_bulk_task.delay(job_id, float(estimated_cost))
    except Exception as e:
        logger.exception("enqueue_failed: %s", e)

    return {
        "job_id": job_id,
        "total": total,
        "estimated_cost": float(estimated_cost),
        "reserve_tx": reserve_tx,
        "team_id": chosen_team,
    }
reserve_tx = reserve_and_deduct(
    user.id,
    estimated_cost,
    reference=f"bulk-reserve:{uuid.uuid4().hex[:8]}",
    team_id=chosen_team,
    job_id=job_id
        )
