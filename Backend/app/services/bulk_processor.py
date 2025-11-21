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
from backend.app.services.storage_s3 import upload_file_local_or_s3
from backend.app.services.domain_backoff import acquire_slot, release_slot, get_backoff_seconds, increase_backoff, clear_backoff

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
        with open(path, "r", encoding="utf-8", errors="ignore") as fh:
            for line in fh:
                line = line.strip()
                if line and "@" in line:
                    emails.append(line.lower())
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
    per_cost = _dec(get_cost_for_key("verify.bulk_per_email") or 0)
    actual_cost = (per_cost * Decimal(actual_count)).quantize(Decimal("0.000001"))
    refund = (estimated_cost - actual_cost).quantize(Decimal("0.000001")) if estimated_cost > actual_cost else Decimal("0")
    if refund > 0:
        try:
            add_credits(job.user_id, refund, reference=f"{job.job_id}:refund_after_processing")
        except Exception:
            logger.exception("refund failed for job %s", job.job_id)
    # upload to S3 if configured
    try:
        if job.output_path and job.output_path.startswith("/"):
            remote_key = f"bulk_results/{os.path.basename(job.output_path)}"
            remote_url = upload_file_local_or_s3(job.output_path, remote_key)
            if remote_url and remote_url != job.output_path:
                job.output_path = remote_url
                db_session.add(job); db_session.commit(); db_session.refresh(job)
    except Exception:
        logger.exception("s3 upload in finalize failed")
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
    vcount = 0
    icount = 0
    pcount = 0
    for email in emails_chunk:
        domain = email.split("@",1)[-1] if "@" in email else None
        # check and observe backoff delay for domain
        backoff = get_backoff_seconds(domain) if domain else 0
        if backoff and backoff > 0:
            time.sleep(min(backoff, 10))  # small sleep to respect polite backoff
        # attempt to acquire slot
        got = acquire_slot(domain) if domain else True
        if not got:
            # if slot not available, wait short and retry once
            time.sleep(1)
            got = acquire_slot(domain) if domain else True
            if not got:
                # treat as temporary skip: mark as invalid here and continue
                append_result(output_path, email, "skipped_throttle", None, "domain_throttle")
                icount += 1
                pcount += 1
                continue

        try:
            res = verify_email_sync(email)
            status = res.get("status", "unknown")
            risk = res.get("risk_score")
            raw = res.get("details") or res.get("raw") or str(res)
            append_result(output_path, email, status, risk, str(raw))
            pcount += 1
            if status == "valid":
                vcount += 1
                clear_backoff(domain)
            else:
                icount += 1
                # if temporary/greylist style (400-499) we bump backoff
                rc = res.get("rcpt_response_code")
                if rc and 400 <= int(rc) < 500:
                    increase_backoff(domain)
        except Exception as e:
            logger.exception("verify failed for %s: %s", email, e)
            append_result(output_path, email, "error", None, str(e))
            pcount += 1
            icount += 1
            # on exception, increase backoff for domain
            try:
                increase_backoff(domain)
            except:
                pass
        finally:
            # release slot regardless
            try:
                release_slot(domain)
            except:
                pass
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

        processed = 0
        valid = 0
        invalid = 0
        for i in range(0, total, CHUNK_SIZE):
            chunk = emails[i:i+CHUNK_SIZE]
            try:
                v, ic, p = process_chunk(chunk, output_path)
            except Exception as e:
                logger.exception("process_chunk failed: %s", e)
                v, ic, p = 0, len(chunk), len(chunk)
            processed += p
            valid += v
            invalid += ic
            job.processed = processed
            job.valid = valid
            job.invalid = invalid
            db.add(job); db.commit(); db.refresh(job)

        job.status = "completed"
        db.add(job); db.commit(); db.refresh(job)

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
