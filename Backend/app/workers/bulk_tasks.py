from backend.app.celery_app import celery_app
from backend.app.services.bulk_processor import submit_bulk_job


@celery_app.task(name="backend.app.workers.bulk_tasks.enqueue_bulk")
def enqueue_bulk(user_id: int, job_id: str, emails: list):
    """
    External entry point if you want to enqueue bulk jobs from Celery.
    Not required for now but kept for scaling.
    """
    return submit_bulk_job(user_id, job_id, emails)
# backend/app/workers/bulk_tasks.py
from backend.app.celery_app import celery_app
from backend.app.services.bulk_processor import process_bulk_job
from decimal import Decimal
import logging

logger = logging.getLogger(__name__)

@celery_app.task(bind=True, max_retries=3)
def process_bulk_task(self, job_id: str, estimated_cost: float):
    """
    Celery wrapper. estimated_cost passed as float to avoid serialization issues.
    """
    try:
        process_bulk_job(job_id, Decimal(str(estimated_cost)))
        return {"ok": True}
    except Exception as e:
        logger.exception("process_bulk_task error: %s", e)
        raise self.retry(countdown=60)


# backend/app/workers/bulk_tasks.py
from backend.app.celery_app import celery_app
from backend.app.db import SessionLocal
from backend.app.models.bulk_job import BulkJob
from backend.app.services.verification_engine import verify_email_sync
from backend.app.services.pricing_service import get_cost_for_key
from backend.app.services.credits_service import add_credits
from backend.app.services.team_billing_service import refund_to_team
from decimal import Decimal, ROUND_HALF_UP
import csv, io, zipfile, os, logging, json

logger = logging.getLogger(__name__)

def _dec(x) -> Decimal:
    return Decimal(str(x)).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)

@celery_app.task(bind=True)
def process_bulk_task(self, job_id: str, estimated_cost: float):
    db = SessionLocal()
    try:
        job = db.query(BulkJob).filter(BulkJob.job_id==job_id).first()
        if not job:
            logger.error("bulk job not found %s", job_id)
            return {"error":"job_not_found"}

        # load input file content
        if not job.input_path or not os.path.exists(job.input_path):
            job.status = "error"
            job.error_message = "input_missing"
            db.add(job); db.commit()
            return {"error":"input_missing"}

        # detect file type
        filename = job.input_path
        emails = []
        try:
            _, ext = os.path.splitext(filename)
            ext = ext.lower()
            with open(job.input_path, "rb") as fh:
                content = fh.read()
            if ext == ".zip":
                z = zipfile.ZipFile(io.BytesIO(content))
                for name in z.namelist():
                    if name.endswith("/") or name.startswith("__MACOSX"):
                        continue
                    if name.lower().endswith((".csv", ".txt")):
                        raw = z.read(name).decode("utf-8", errors="ignore")
                        for line in raw.splitlines():
                            s = line.strip()
                            if s and "@" in s:
                                emails.append(s)
            elif ext in (".csv", ".txt"):
                raw = content.decode("utf-8", errors="ignore")
                reader = csv.reader(io.StringIO(raw))
                for row in reader:
                    for col in row:
                        v = col.strip()
                        if v and "@" in v:
                            emails.append(v)
                            break
            else:
                raw = content.decode("utf-8", errors="ignore")
                for line in raw.splitlines():
                    s = line.strip()
                    if s and "@" in s:
                        emails.append(s)
        except Exception as e:
            logger.exception("worker parse failed: %s", e)
            job.status = "error"
            job.error_message = "parse_failed"
            db.add(job); db.commit()
            return {"error":"parse_failed"}

        emails = list(dict.fromkeys([e.lower().strip() for e in emails if "@" in e]))
        total = len(emails)
        if total == 0:
            job.status = "done"
            job.processed = 0
            job.valid = 0
            job.invalid = 0
            job.output_path = None
            db.add(job); db.commit()
            return {"error":"no_emails"}

        # run verify_email_sync for each email (consider batching & concurrency)
        valid = 0; invalid = 0
        results = []
        for e in emails:
            try:
                r = verify_email_sync(e, user_id=job.user_id)
                results.append({"email":e, "result": r})
                if r.get("status") == "valid":
                    valid += 1
                else:
                    invalid += 1
            except Exception as ex:
                results.append({"email": e, "error": "verify_failed"})
                invalid += 1

        # write output CSV
        out_fname = f"{job.job_id}-out.csv"
        out_path = os.path.join(os.path.dirname(job.input_path), out_fname)
        try:
            with open(out_path, "w", newline="", encoding="utf-8") as wf:
                writer = csv.writer(wf)
                writer.writerow(["email", "status", "risk_score", "raw"])
                for r in results:
                    email = r.get("email")
                    res = r.get("result") or {}
                    writer.writerow([email, res.get("status"), res.get("risk_score"), json.dumps(res.get("details") or res.get("raw") or "")])
        except Exception as e:
            logger.exception("write out failed: %s", e)
            job.status = "error"
            job.error_message = "write_output_failed"
            db.add(job); db.commit()
            return {"error":"write_output_failed"}

        # finalize job row
        job.status = "done"
        job.processed = total
        job.valid = valid
        job.invalid = invalid
        job.output_path = out_path
        db.add(job)
        db.commit()

        # compute actual cost and refund difference (if reservation earlier was from team or user)
        per_cost = _dec(get_cost_for_key("verify.bulk_per_email") or 0)
        actual_cost = (per_cost * Decimal(total)).quantize(Decimal("0.000001"))
        estimated = Decimal(str(estimated_cost)).quantize(Decimal("0.000001"))
        refund_amount = (estimated - actual_cost) if estimated > actual_cost else Decimal("0")

        if refund_amount > 0:
            # if job has team_id, refund to team; else refund to user
            try:
                if getattr(job, "team_id", None):
                    refund_to_team(job.team_id, refund_amount, reference=f"{job.job_id}:refund")
                else:
                    add_credits(job.user_id, refund_amount, reference=f"{job.job_id}:refund")
            except Exception:
                logger.exception("refund finalize failed for %s", job.job_id)

        return {"job_id": job.job_id, "processed": total, "valid": valid, "invalid": invalid}

    finally:
        db.close()


# backend/app/workers/bulk_tasks.py
import os
import io
import csv
import zipfile
import logging
from decimal import Decimal, ROUND_HALF_UP
from typing import List
from celery import Task

from backend.app.celery_app import celery_app
from backend.app.db import SessionLocal
from backend.app.models.bulk_job import BulkJob
from backend.app.services.verification_engine import verify_email_sync
from backend.app.services.team_billing_service import add_team_credits
from backend.app.services.credits_service import add_credits
from backend.app.services.webhook_sender import webhook_task
from backend.app.services.pricing_service import get_cost_for_key
from backend.app.config import settings

logger = logging.getLogger(__name__)
INPUT_FOLDER = getattr(settings, "BULK_INPUT_FOLDER", "/tmp/bulk_inputs")
OUTPUT_FOLDER = getattr(settings, "BULK_OUTPUT_FOLDER", "/tmp/bulk_outputs")
os.makedirs(INPUT_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

def _dec(x) -> Decimal:
    return Decimal(str(x)).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)

def _parse_emails_from_text(text: str) -> List[str]:
    lines = []
    for line in text.splitlines():
        s = line.strip()
        if s and "@" in s:
            lines.append(s)
    return lines

def _parse_emails_from_zip(content: bytes) -> List[str]:
    emails = []
    z = zipfile.ZipFile(io.BytesIO(content))
    for name in z.namelist():
        if name.endswith("/") or name.startswith("__MACOSX"):
            continue
        if name.lower().endswith((".csv", ".txt")):
            raw = z.read(name).decode("utf-8", errors="ignore")
            if name.lower().endswith(".csv"):
                for row in csv.reader(io.StringIO(raw)):
                    for col in row:
                        v = col.strip()
                        if v and "@" in v:
                            emails.append(v)
                            break
            else:
                emails.extend(_parse_emails_from_text(raw))
    return emails

@celery_app.task(bind=True, max_retries=3, name="process_bulk_task")
def process_bulk_task(self: Task, job_id: str, estimated_cost: float = 0.0):
    """
    Worker: process a BulkJob (reads input_path, verifies emails, writes output CSV,
    updates BulkJob counters, calculates actual cost, and refunds difference to user/team).
    Args:
      - job_id: BulkJob.job_id (string)
      - estimated_cost: float (for logging only; actual cost computed)
    """
    db = SessionLocal()
    try:
        job = db.query(BulkJob).filter(BulkJob.job_id == job_id).first()
        if not job:
            logger.error("process_bulk_task: job not found %s", job_id)
            return {"error": "job_not_found"}

        job.status = "processing"
        db.add(job); db.commit()

        # Read input file
        if not job.input_path or not os.path.exists(job.input_path):
            job.status = "failed"
            job.error_message = "input_file_missing"
            db.add(job); db.commit()
            return {"error": "input_missing"}

        # read bytes
        with open(job.input_path, "rb") as fh:
            content = fh.read()

        # parse emails safely
        emails = []
        _, ext = os.path.splitext(job.input_path.lower())
        try:
            if ext == ".zip":
                emails = _parse_emails_from_zip(content)
            elif ext in (".csv", ".txt"):
                raw = content.decode("utf-8", errors="ignore")
                for row in csv.reader(io.StringIO(raw)):
                    for col in row:
                        v = col.strip()
                        if v and "@" in v:
                            emails.append(v)
                            break
            else:
                raw = content.decode("utf-8", errors="ignore")
                emails = _parse_emails_from_text(raw)
        except Exception as e:
            logger.exception("parse input failed: %s", e)
            job.status = "failed"
            job.error_message = "parse_failed"
            db.add(job); db.commit()
            return {"error": "parse_failed"}

        # sanitize/dedupe
        emails = [e.strip().lower() for e in emails if "@" in e]
        emails = list(dict.fromkeys(emails))
        total = len(emails)
        job.total = total
        job.processed = 0
        job.valid = 0
        job.invalid = 0
        db.add(job); db.commit()

        # cost per email from pricing map
        per_cost = _dec(get_cost_for_key("verify.bulk_per_email") or 0)
        actual_cost_total = Decimal("0")

        output_rows = []
        for idx, email in enumerate(emails):
            try:
                res = verify_email_sync(email, user_id=job.user_id)
                status = res.get("status", "unknown")
                risk = res.get("risk_score")
                output_rows.append({"email": email, "status": status, "risk_score": risk, "raw": res.get("details") or res.get("raw") or ""})
                job.processed += 1
                if status == "valid":
                    job.valid += 1
                else:
                    job.invalid += 1
                actual_cost_total += per_cost
            except Exception as e:
                logger.exception("verify failed for %s: %s", email, e)
                output_rows.append({"email": email, "status": "error", "risk_score": None, "raw": "verify_exception"})
                job.processed += 1
                job.invalid += 1
            # persist progress periodically
            if idx % 50 == 0:
                db.add(job); db.commit()

        # write output CSV
        out_fname = f"{job.job_id}-results.csv"
        out_path = os.path.join(OUTPUT_FOLDER, out_fname)
        with open(out_path, "w", newline='', encoding='utf-8') as outfh:
            writer = csv.DictWriter(outfh, fieldnames=["email", "status", "risk_score", "raw"])
            writer.writeheader()
            for r in output_rows:
                writer.writerow(r)

        job.output_path = out_path
        job.status = "finished"
        db.add(job); db.commit()

        # compute refund (if any).
        est = Decimal(str(estimated_cost)) if estimated_cost else _dec(per_cost * Decimal(total))
        actual = actual_cost_total.quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)
        refund = (est - actual) if est > actual else Decimal("0")

        # Refund to team or user
        if refund > 0:
            try:
                if getattr(job, "team_id", None):
                    add_team_credits(job.team_id, refund, reference=f"{job.job_id}:refund_worker")
                else:
                    add_credits(job.user_id, refund, reference=f"{job.job_id}:refund_worker")
            except Exception as e:
                logger.exception("refund failed for %s: %s", job.job_id, e)

        # send webhook (best-effort)
        if job.webhook_url:
            try:
                webhook_task.delay(job.webhook_url, {"event":"bulk.finished","job_id": job.job_id, "total": job.total, "valid": job.valid, "invalid": job.invalid})
            except Exception:
                logger.exception("webhook task enqueue failed for %s", job.job_id)

        return {"job_id": job.job_id, "total": job.total, "valid": job.valid, "invalid": job.invalid, "output_path": out_path}

    except Exception as exc:
        logger.exception("bulk worker failed for job %s: %s", job_id, exc)
        try:
            job.status = "failed"
            job.error_message = str(exc)
            db.add(job); db.commit()
        except Exception:
            pass
        raise self.retry(exc=exc, countdown=60)
    finally:
        db.close()




