
import uuid
import logging
from typing import List, Optional
from fastapi import HTTPException

from backend.app.celery_app import celery_app
from backend.app.services.credits_service import reserve_credits
from backend.app.services.credits_service import COST_PER_VERIFICATION, capture_reservation

logger = logging.getLogger(__name__)

# Celery task name (worker implements verify_email_task)
VERIFY_TASK_NAME = "backend.app.workers.tasks.verify_email_task"

def submit_bulk_job(user_id: int, job_id: str, emails: List[str], meta: Optional[dict] = None) -> dict:
    """
    Reserve credits for the bulk job, then enqueue tasks.
    If reservation fails (insufficient credits), raise HTTPException(402).
    """
    meta = meta or {}
    count = len(emails)
    total_cost = COST_PER_VERIFICATION * count

    # Reserve credits (throws HTTPException(402) if not enough)
    db = None
    try:
        from backend.app.db import SessionLocal
        db = SessionLocal()
        reservation = reserve_credits(db, user_id, total_cost, job_id=job_id, reference=job_id)
    except HTTPException:
        # bubble up to caller (API will return 402)
        raise
    except Exception as e:
        logger.exception("Failed to reserve credits: %s", e)
        raise HTTPException(status_code=500, detail="reserve_failed")
    finally:
        if db:
            db.close()

    queued = 0
    # enqueue tasks
    for email in emails:
        try:
            celery_app.send_task(VERIFY_TASK_NAME, args=[email, {"user_id": user_id, "job_id": job_id, "reservation_id": reservation.id}])
            queued += 1
        except Exception as e:
            logger.exception("Failed to enqueue verify task for %s: %s", email, e)
            continue

    # Return job info (reservation id can be used to capture when done)
    return {"job_id": job_id, "queued": queued, "reservation_id": reservation.id}



# backend/app/services/bulk_processor.py
import csv, os, math, time, logging
from decimal import Decimal, ROUND_HALF_UP
from typing import List
from backend.app.db import SessionLocal
from backend.app.models.bulk_job import BulkJob
from backend.app.models.verification_result import VerificationResult
from backend.app.services.verification_engine import verify_email_sync
from backend.app.services.pricing_service import get_cost_for_key
from backend.app.services.credits_service import add_credits
from backend.app.services.webhook_sender import webhook_task
from backend.app.config import settings

logger = logging.getLogger(__name__)

CHUNK_SIZE = int(getattr(settings, "BULK_CHUNK_SIZE", 200))
RESULTS_FOLDER = getattr(settings, "BULK_RESULTS_FOLDER", "/tmp/bulk_results")

os.makedirs(RESULTS_FOLDER, exist_ok=True)

def _dec(x) -> Decimal:
    return Decimal(str(x)).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)

def read_emails_from_path(path: str) -> List[str]:
    emails = []
    _, ext = os.path.splitext(path.lower())
    if ext == ".csv" or ext == ".txt":
        with open(path, "r", encoding="utf-8", errors="ignore") as fh:
            reader = csv.reader(fh)
            for row in reader:
                for col in row:
                    v = col.strip()
                    if v and "@" in v:
                        emails.append(v.lower())
                        break
    else:
        # fallback: read lines
        with open(path, "r", encoding="utf-8", errors="ignore") as fh:
            for line in fh:
                line = line.strip()
                if line and "@" in line:
                    emails.append(line.lower())
    # dedupe
    seen = set()
    out = []
    for e in emails:
        if e not in seen:
            seen.add(e)
            out.append(e)
    return out

def write_results_header(path: str):
    with open(path, "w", newline='', encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["email", "status", "risk_score", "raw_json"])

def append_result(path: str, email: str, status: str, risk_score, raw_json: str):
    with open(path, "a", newline='', encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow([email, status, risk_score, raw_json])

def finalize_job_and_refund(db_session, job: BulkJob, estimated_cost: Decimal, actual_count: int):
    """
    Compute actual_cost = cost_per_email * actual_count
    refund = estimated_cost - actual_cost
    Add credits for refund if > 0 and update job stats (already updated during processing)
    """
    per_cost = _dec(get_cost_for_key("verify.bulk_per_email") or 0)
    actual_cost = (per_cost * Decimal(actual_count)).quantize(Decimal("0.000001"))
    refund = (estimated_cost - actual_cost).quantize(Decimal("0.000001")) if estimated_cost > actual_cost else Decimal("0")
    if refund > 0:
        try:
            add_credits(job.user_id, refund, reference=f"{job.job_id}:refund_after_processing")
        except Exception:
            logger.exception("refund failed for job %s", job.job_id)
    # send webhook if configured
    if job.webhook_url:
        payload = {
            "job_id": job.job_id,
            "status": job.status,
            "total": job.total,
            "processed": job.processed,
            "valid": job.valid,
            "invalid": job.invalid,
            "output_path": job.output_path
        }
        try:
            webhook_task.delay(job.webhook_url, payload)
        except Exception:
            logger.exception("webhook enqueue failed for %s", job.job_id)

def process_chunk(emails_chunk: List[str], output_path: str):
    """
    Process a small chunk, return tuple(valid_count, invalid_count, processed_count)
    """
    vcount = 0
    icount = 0
    pcount = 0
    for email in emails_chunk:
        try:
            res = verify_email_sync(email)
            status = res.get("status", "unknown")
            risk = res.get("risk_score")
            raw = res.get("details") or res.get("raw") or str(res)
            append_result(output_path, email, status, risk, str(raw))
            pcount += 1
            if status == "valid":
                vcount += 1
            else:
                icount += 1
        except Exception as e:
            logger.exception("verify failed for %s: %s", email, e)
            append_result(output_path, email, "error", None, str(e))
            pcount += 1
            icount += 1
    return vcount, icount, pcount

def process_bulk_job(job_id: str, estimated_cost: Decimal):
    db = SessionLocal()
    try:
        job = db.query(BulkJob).filter(BulkJob.job_id == job_id).first()
        if not job:
            logger.error("bulk job not found %s", job_id)
            return
        job.status = "running"
        db.add(job); db.commit(); db.refresh(job)

        emails = read_emails_from_path(job.input_path)
        total = len(emails)
        job.total = total
        db.add(job); db.commit(); db.refresh(job)

        output_fname = f"{job.job_id}.results.csv"
        output_path = os.path.join(RESULTS_FOLDER, output_fname)
        write_results_header(output_path)
        job.output_path = output_path
        db.add(job); db.commit(); db.refresh(job)

        # process in chunks
        chunks = math.ceil(total / CHUNK_SIZE) if CHUNK_SIZE > 0 else 1
        processed = 0
        valid = 0
        invalid = 0
        for i in range(0, total, CHUNK_SIZE):
            chunk = emails[i:i+CHUNK_SIZE]
            # simple backoff for heavy hosts — could add adaptive backoff logic here
            try:
                v, ic, p = process_chunk(chunk, output_path)
            except Exception as e:
                logger.exception("process_chunk failed: %s", e)
                # conservative: mark all chunk as processed but failed
                v, ic, p = 0, len(chunk), len(chunk)
            processed += p
            valid += v
            invalid += ic
            # update DB after each chunk
            job.processed = processed
            job.valid = valid
            job.invalid = invalid
            db.add(job); db.commit(); db.refresh(job)

        job.status = "completed"
        db.add(job); db.commit(); db.refresh(job)

        # finalize: compute refunds & send webhook
        finalize_job_and_refund(db, job, estimated_cost, actual_count=total)

    except Exception as e:
        logger.exception("bulk job processor failed: %s", e)
        try:
            job.status = "failed"
            job.error_message = str(e)
            db.add(job); db.commit()
        except Exception:
            pass
    finally:
        db.close()

