# backend/app/services/bulk_processor.py

import csv
import os
import time
import logging
import queue
import threading
from decimal import Decimal, ROUND_HALF_UP
from typing import List, Optional, Tuple, Any
from pathlib import Path
import inspect

# ---------------------------------------------------------
# PROMETHEUS METRICS
# ---------------------------------------------------------
from prometheus_client import Counter, Histogram

# Bulk job lifecycle
BULK_JOB_TOTAL = Counter(
    "bulk_job_total",
    "Bulk job lifecycle",
    ["status"]  # queued|running|completed|failed
)

# Chunk-level metrics
BULK_CHUNK_LATENCY = Histogram(
    "bulk_chunk_latency_seconds",
    "Processing latency for each chunk"
)

BULK_CHUNK_EMAIL_TOTAL = Counter(
    "bulk_chunk_email_total",
    "Emails processed in bulk chunks",
    ["result"]  # valid|invalid|error
)

# Email verify + output write metrics
BULK_CSV_WRITE_TOTAL = Counter(
    "bulk_csv_write_total",
    "CSV rows written by bulk jobs",
    ["result"]  # ok|error
)

# Domain throttling
BULK_SLOT_THROTTLE_TOTAL = Counter(
    "bulk_slot_throttle_total",
    "Emails skipped due to domain throttle",
    ["domain"]
)

BULK_BACKOFF_SECONDS = Histogram(
    "bulk_backoff_seconds",
    "Domain backoff seconds observed in bulk pipeline",
    ["domain"]
)

# Entire job latency
BULK_JOB_LATENCY = Histogram(
    "bulk_job_latency_seconds",
    "Total processing time for a bulk job"
)

# Job failure counter
BULK_JOB_FAILURE_TOTAL = Counter(
    "bulk_job_failure_total",
    "Bulk job failures"
)

# ---------------------------------------------------------
# ORIGINAL IMPORTS (unchanged)
# ---------------------------------------------------------
from backend.app.db import SessionLocal
from backend.app.models.bulk_job import BulkJob
from backend.app.models.verification_result import VerificationResult

from backend.app.services.verification_engine import verify_email_sync
from backend.app.services.pricing_service import get_cost_for_key
from backend.app.services.webhook_sender import webhook_task
from backend.app.services.storage_s3 import upload_file_local_or_s3
from backend.app.services.domain_backoff import (
    acquire_slot,
    release_slot,
    get_backoff_seconds,
    increase_backoff,
    clear_backoff,
)
from backend.app.services.credits_service import add_credits
from backend.app.config import settings

logger = logging.getLogger(__name__)

CHUNK_SIZE = int(getattr(settings, "BULK_CHUNK_SIZE", 200))
RESULTS_FOLDER = getattr(settings, "BULK_RESULTS_FOLDER", "/tmp/bulk_results")
os.makedirs(RESULTS_FOLDER, exist_ok=True)


# ---------------------------------------------------------
# Helpers
# ---------------------------------------------------------

def _dec(x) -> Decimal:
    return Decimal(str(x)).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)


def json_safe_str(v: Any) -> str:
    try:
        import json as _json
        if isinstance(v, (dict, list)):
            return _json.dumps(v, ensure_ascii=False)
        return str(v)
    except Exception:
        return str(v)


def _call_add_credits(user_id: int, amount: Decimal, reference: str = None) -> bool:
    """Call add_credits (async or sync)."""
    try:
        if inspect.iscoroutinefunction(add_credits):
            import asyncio
            asyncio.run(add_credits(user_id, amount, reference=reference))
        else:
            add_credits(user_id, amount, reference=reference)
        return True
    except Exception as e:
        logger.exception("add_credits wrapper failed: %s", e)
        return False


# ---------------------------------------------------------
# CSV Writer Thread
# ---------------------------------------------------------

class CSVWriterThread(threading.Thread):
    def __init__(self, out_path: str, q: "queue.Queue", header: List[str]):
        super().__init__(daemon=True)
        self.out_path = out_path
        self.q = q
        self.header = header
        self._stop = threading.Event()

    def run(self):
        Path(self.out_path).parent.mkdir(parents=True, exist_ok=True)

        with open(self.out_path, "a", newline="", encoding="utf-8") as fh:
            writer = csv.writer(fh)

            fh.seek(0, os.SEEK_END)
            if fh.tell() == 0:
                writer.writerow(self.header)

            while not self._stop.is_set():
                try:
                    item = self.q.get(timeout=1.0)
                except queue.Empty:
                    continue

                if item is None:
                    self.q.task_done()
                    break

                try:
                    writer.writerow(item)
                    BULK_CSV_WRITE_TOTAL.labels(result="ok").inc()
                except Exception:
                    BULK_CSV_WRITE_TOTAL.labels(result="error").inc()
                    try:
                        fh.write(",".join([str(x) for x in item]) + "\n")
                    except Exception as e:
                        logger.exception("CSV fallback write failed: %s", e)
                finally:
                    self.q.task_done()

    def stop(self):
        self._stop.set()


# ---------------------------------------------------------
# File Reader
# ---------------------------------------------------------

def read_emails_from_path(path: str):
    emails = []
    _, ext = os.path.splitext(path.lower())

    try:
        if ext in (".csv", ".txt"):
            with open(path, "r", encoding="utf-8", errors="ignore") as fh:
                for row in csv.reader(fh):
                    for col in row:
                        v = (col or "").strip()
                        if v and "@" in v:
                            emails.append(v.lower())
                            break
        else:
            with open(path, "r", encoding="utf-8", errors="ignore") as fh:
                for line in fh:
                    line = line.strip()
                    if line and "@" in line:
                        emails.append(line.lower())
    except Exception as e:
        logger.exception("read_emails_from_path failed: %s", e)
        raise

    seen = set()
    out = []
    for e in emails:
        if e not in seen:
            seen.add(e)
            out.append(e)

    return out


# ---------------------------------------------------------
# Chunk Processor
# ---------------------------------------------------------

def process_chunk(emails_chunk: List[str], output_queue: "queue.Queue", output_path: str) -> Tuple[int, int, int]:
    start_chunk = time.time()

    vcount = 0
    icount = 0
    pcount = 0

    for email in emails_chunk:
        domain = email.split("@", 1)[-1] if "@" in email else None

        try:
            backoff = get_backoff_seconds(domain) if domain else 0
        except Exception:
            backoff = 0

        if backoff > 0:
            BULK_BACKOFF_SECONDS.labels(domain=domain).observe(backoff)
            time.sleep(min(backoff, 10))

        got = acquire_slot(domain) if domain else True
        if not got:
            BULK_SLOT_THROTTLE_TOTAL.labels(domain=domain).inc()
            output_queue.put((email, "skipped_throttle", None, "domain_throttle"))
            icount += 1
            pcount += 1
            continue

        try:
            res = verify_email_sync(email)
            status = res.get("status", "unknown")
            risk = res.get("risk_score")
            raw = res.get("details") or res.get("raw") or str(res)

            output_queue.put((email, status, risk, json_safe_str(raw)))
            pcount += 1

            if status == "valid":
                BULK_CHUNK_EMAIL_TOTAL.labels(result="valid").inc()
                vcount += 1
                clear_backoff(domain)
            else:
                BULK_CHUNK_EMAIL_TOTAL.labels(result="invalid").inc()
                icount += 1
                rc = res.get("rcpt_response_code") or res.get("rcpt_code")
                try:
                    rc_int = int(rc) if rc is not None else None
                except Exception:
                    rc_int = None
                if rc_int and 400 <= rc_int < 500:
                    increase_backoff(domain)

        except Exception as e:
            logger.exception("verify failed for %s: %s", email, e)
            BULK_CHUNK_EMAIL_TOTAL.labels(result="error").inc()
            output_queue.put((email, "error", None, str(e)))
            pcount += 1
            icount += 1
            increase_backoff(domain)
        finally:
            release_slot(domain)

    BULK_CHUNK_LATENCY.observe(time.time() - start_chunk)
    return vcount, icount, pcount


# ---------------------------------------------------------
# Finalize Job
# ---------------------------------------------------------

def finalize_job_and_refund(db_session, job: BulkJob, estimated_cost: Decimal, actual_count: int):
    per_cost = _dec(get_cost_for_key("verify.bulk_per_email") or 0)
    actual_cost = (per_cost * Decimal(actual_count)).quantize(Decimal("0.000001"))
    refund = (estimated_cost - actual_cost) if estimated_cost > actual_cost else Decimal("0")

    if refund > 0:
        _call_add_credits(job.user_id, refund, reference=f"{job.job_id}:refund_after_processing")

    try:
        if job.output_path and job.output_path.startswith("/"):
            remote_key = f"bulk_results/{os.path.basename(job.output_path)}"
            remote_url = upload_file_local_or_s3(job.output_path, remote_key)
            if remote_url and remote_url != job.output_path:
                job.output_path = remote_url
                db_session.add(job)
                db_session.commit()
    except Exception:
        logger.exception("S3 upload failed")

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
            try:
                webhook_task.delay(job.webhook_url, payload)
            except Exception:
                webhook_task(job.webhook_url, payload)
        except Exception:
            logger.exception("Webhook dispatch failed")


# ---------------------------------------------------------
# MAIN ENTRY POINT
# ---------------------------------------------------------

def process_bulk_job(job_id: str, estimated_cost: Decimal):
    start_job = time.time()

    db = SessionLocal()
    writer_q = queue.Queue()
    writer_thread = None
    job = None

    try:
        job = db.query(BulkJob).filter(BulkJob.job_id == job_id).first()
        if not job:
            logger.error("Bulk job not found: %s", job_id)
            return

        BULK_JOB_TOTAL.labels(status="running").inc()

        job.status = "running"
        db.add(job)
        db.commit()

        emails = read_emails_from_path(job.input_path)
        total = len(emails)
        job.total = total
        db.add(job)
        db.commit()

        output_fname = f"{job.job_id}.results.csv"
        output_path = os.path.join(RESULTS_FOLDER, output_fname)

        header = ["email", "status", "risk_score", "raw_json"]
        writer_thread = CSVWriterThread(output_path, writer_q, header)
        writer_thread.start()

        job.output_path = output_path
        db.add(job)
        db.commit()

        processed = valid = invalid = 0

        for i in range(0, total, CHUNK_SIZE):
            chunk = emails[i:i + CHUNK_SIZE]

            try:
                v, ic, p = process_chunk(chunk, writer_q, output_path)
            except Exception:
                v, ic, p = 0, len(chunk), len(chunk)

            processed += p
            valid += v
            invalid += ic

            job.processed = processed
            job.valid = valid
            job.invalid = invalid
            db.add(job)
            db.commit()

        job.status = "completed"
        db.add(job)
        db.commit()

        finalize_job_and_refund(db, job, estimated_cost, actual_count=total)

        BULK_JOB_TOTAL.labels(status="completed").inc()
        BULK_JOB_LATENCY.observe(time.time() - start_job)

    except Exception as e:
        logger.exception("Bulk job failed: %s", e)
        BULK_JOB_TOTAL.labels(status="failed").inc()
        BULK_JOB_FAILURE_TOTAL.inc()

        if job:
            job.status = "failed"
            job.error_message = str(e)
            db.add(job)
            db.commit()

    finally:
        try:
            writer_q.put(None)
            writer_q.join()
            writer_thread.stop()
            writer_thread.join(timeout=5)
        except Exception:
            pass

        db.close()
        logger.info("Bulk job cleanup complete for %s", job_id)
