# backend/app/services/bulk_processor.py
"""
Bulk job processor (production-grade)

Key improvements:
- single-writer CSV via background thread + queue (no interleaving / corruption)
- robust CSV writer (uses csv.writer)
- safe add_credits wrapper (handles sync or async add_credits)
- graceful cancellation and error handling (job status updated)
- reasonable logging
"""

import csv
import os
import time
import logging
import queue
import threading
from decimal import Decimal, ROUND_HALF_UP
from typing import List, Optional, Tuple, Any, Dict
from pathlib import Path
import inspect

from backend.app.db import SessionLocal
from backend.app.models.bulk_job import BulkJob
from backend.app.models.verification_result import VerificationResult

# Use the verification engine sync wrapper (keeps compatibility)
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
from backend.app.services.credits_service import add_credits  # could be sync or async

from backend.app.config import settings

logger = logging.getLogger(__name__)

CHUNK_SIZE = int(getattr(settings, "BULK_CHUNK_SIZE", 200))
RESULTS_FOLDER = getattr(settings, "BULK_RESULTS_FOLDER", "/tmp/bulk_results")
os.makedirs(RESULTS_FOLDER, exist_ok=True)

# ---------------------------------------------------------
# Decimal helper
# ---------------------------------------------------------
def _dec(x) -> Decimal:
    return Decimal(str(x)).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)

# ---------------------------------------------------------
# Safe add_credits wrapper (supports sync or async implementations)
# ---------------------------------------------------------
def _call_add_credits(user_id: int, amount: Decimal, reference: str = None, type_: str = "topup", metadata: Any = None) -> bool:
    """
    Call add_credits regardless of whether it's async or sync in your codebase.
    Returns True on success, False on failure.
    """
    try:
        if inspect.iscoroutinefunction(add_credits):
            # run coroutine to completion
            import asyncio
            asyncio.run(add_credits(user_id, amount, reference=reference))
        else:
            # sync call
            add_credits(user_id, amount, reference=reference)
        return True
    except Exception as e:
        logger.exception("add_credits wrapper failed: %s", e)
        return False

# ---------------------------------------------------------
# CSV writer thread (single writer to avoid race conditions)
# ---------------------------------------------------------
class CSVWriterThread(threading.Thread):
    def __init__(self, out_path: str, q: "queue.Queue[Optional[Tuple[str,str,Optional[float],str]]]", header: List[str]):
        super().__init__(daemon=True)
        self.out_path = out_path
        self.q = q
        self.header = header
        self._stop = threading.Event()

    def run(self):
        # Ensure dir exists
        Path(self.out_path).parent.mkdir(parents=True, exist_ok=True)
        # Open file once and write rows sequentially
        with open(self.out_path, "a", newline="", encoding="utf-8") as fh:
            writer = csv.writer(fh)
            # If file is empty, write header
            try:
                fh.seek(0, os.SEEK_END)
                if fh.tell() == 0:
                    writer.writerow(self.header)
            except Exception:
                pass

            while not self._stop.is_set():
                try:
                    item = self.q.get(timeout=1.0)
                except queue.Empty:
                    continue

                if item is None:
                    # sentinel => finish
                    self.q.task_done()
                    break

                # item expected: (email, status, risk_score, raw_json)
                try:
                    writer.writerow(item)
                except Exception as e:
                    # best-effort: write a fallback line
                    try:
                        fh.write(",".join([str(x) for x in item]) + "\n")
                    except Exception:
                        logger.exception("CSV write fallback failed: %s", e)
                finally:
                    self.q.task_done()

    def stop(self):
        self._stop.set()

# ---------------------------------------------------------
# File utilities
# ---------------------------------------------------------
def read_emails_from_path(path: str):
    """Read and dedupe emails from a local CSV or text file (sync)."""
    emails = []
    _, ext = os.path.splitext(path.lower())
    try:
        if ext == ".csv" or ext == ".txt":
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

    # dedupe preserving order
    seen = set()
    out = []
    for e in emails:
        if e not in seen:
            seen.add(e)
            out.append(e)
    return out

# ---------------------------------------------------------
# Writer helper wrappers
# ---------------------------------------------------------
def write_results_header(path: str):
    # header is written by writer thread when file empty
    pass

# ---------------------------------------------------------
# Core chunk processing (sync)
# ---------------------------------------------------------
def process_chunk(emails_chunk: List[str], output_queue: "queue.Queue", output_path: str) -> Tuple[int, int, int]:
    """
    Process a chunk of emails synchronously (calls verify_email_sync).
    Returns (valid_count, invalid_count, processed_count)
    """
    vcount = 0
    icount = 0
    pcount = 0

    for email in emails_chunk:
        domain = email.split("@", 1)[-1] if "@" in email else None

        # Observe backoff if any
        try:
            backoff = get_backoff_seconds(domain) if domain else 0
        except Exception:
            backoff = 0

        if backoff and backoff > 0:
            time.sleep(min(backoff, 10))

        # Acquire slot for domain
        got = acquire_slot(domain) if domain else True
        if not got:
            # mark skipped_throttle
            output_queue.put((email, "skipped_throttle", None, "domain_throttle"))
            icount += 1
            pcount += 1
            continue

        try:
            res = verify_email_sync(email)
            status = res.get("status", "unknown")
            risk = res.get("risk_score")
            raw = res.get("details") or res.get("raw") or str(res)
            # Serialize raw safely as string (writer will handle quoting)
            output_queue.put((email, status, risk, json_safe_str(raw)))
            pcount += 1
            if status == "valid":
                vcount += 1
                try:
                    clear_backoff(domain)
                except Exception:
                    pass
            else:
                icount += 1
                rc = res.get("rcpt_response_code") or res.get("rcpt_code") or res.get("rc")
                try:
                    rc_int = int(rc) if rc is not None else None
                except Exception:
                    rc_int = None
                if rc_int and 400 <= rc_int < 500:
                    try:
                        increase_backoff(domain)
                    except Exception:
                        pass

        except Exception as e:
            logger.exception("verify failed for %s: %s", email, e)
            output_queue.put((email, "error", None, str(e)))
            pcount += 1
            icount += 1
            try:
                increase_backoff(domain)
            except Exception:
                pass
        finally:
            try:
                release_slot(domain)
            except Exception:
                pass

    return vcount, icount, pcount

# small helper to ensure string serialization for CSV
def json_safe_str(v: Any) -> str:
    try:
        import json as _json
        if isinstance(v, (dict, list)):
            return _json.dumps(v, ensure_ascii=False)
        return str(v)
    except Exception:
        return str(v)

# ---------------------------------------------------------
# Finalize job: refunds, upload, webhook
# ---------------------------------------------------------
def finalize_job_and_refund(db_session, job: BulkJob, estimated_cost: Decimal, actual_count: int):
    per_cost = _dec(get_cost_for_key("verify.bulk_per_email") or 0)
    actual_cost = (per_cost * Decimal(actual_count)).quantize(Decimal("0.000001"))
    refund = (estimated_cost - actual_cost).quantize(Decimal("0.000001")) if estimated_cost > actual_cost else Decimal("0")
    if refund > 0:
        try:
            ok = _call_add_credits(job.user_id, refund, reference=f"{job.job_id}:refund_after_processing")
            if not ok:
                logger.warning("refund call failed for job %s refund=%s", job.job_id, refund)
        except Exception:
            logger.exception("refund failed for job %s", job.job_id)

    # attempt upload to S3 (if configured)
    try:
        if job.output_path and job.output_path.startswith("/"):
            remote_key = f"bulk_results/{os.path.basename(job.output_path)}"
            remote_url = upload_file_local_or_s3(job.output_path, remote_key)
            if remote_url and remote_url != job.output_path:
                job.output_path = remote_url
                db_session.add(job)
                db_session.commit()
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
            # webhook_task may be a celery task; call .delay or run sync try/catch
            try:
                webhook_task.delay(job.webhook_url, payload)
            except Exception:
                # fallback: call sync function
                webhook_task(job.webhook_url, payload)
        except Exception:
            logger.exception("webhook enqueue failed for %s", job.job_id)

# ---------------------------------------------------------
# Main processing entry (to be invoked by worker)
# This function is intentionally synchronous (safe for Celery workers)
# ---------------------------------------------------------
def process_bulk_job(job_id: str, estimated_cost: Decimal):
    db = SessionLocal()
    writer_q: "queue.Queue[Optional[Tuple[str,str,Optional[float],str]]]" = queue.Queue()
    writer_thread: Optional[CSVWriterThread] = None
    job: Optional[BulkJob] = None

    try:
        job = db.query(BulkJob).filter(BulkJob.job_id == job_id).first()
        if not job:
            logger.error("bulk job not found %s", job_id)
            return

        # mark running
        job.status = "running"
        db.add(job)
        db.commit()
        db.refresh(job)

        # read emails (may be large - you can change to streaming if needed)
        emails = read_emails_from_path(job.input_path)
        total = len(emails)
        job.total = total
        db.add(job)
        db.commit()
        db.refresh(job)

        # prepare output file and writer thread
        output_fname = f"{job.job_id}.results.csv"
        output_path = os.path.join(RESULTS_FOLDER, output_fname)

        # create writer thread and start it
        header = ["email", "status", "risk_score", "raw_json"]
        writer_thread = CSVWriterThread(output_path, writer_q, header)
        writer_thread.start()

        # set job output_path immediately (local path)
        job.output_path = output_path
        db.add(job)
        db.commit()
        db.refresh(job)

        processed = 0
        valid = 0
        invalid = 0

        # iterate in chunks
        for i in range(0, total, CHUNK_SIZE):
            chunk = emails[i:i + CHUNK_SIZE]
            try:
                v, ic, p = process_chunk(chunk, writer_q, output_path)
            except Exception as e:
                logger.exception("process_chunk failed: %s", e)
                # mark the whole chunk as failed (best-effort)
                v, ic, p = 0, len(chunk), len(chunk)

            processed += p
            valid += v
            invalid += ic

            # persist progress less frequently if you like — here per-chunk
            job.processed = processed
            job.valid = valid
            job.invalid = invalid
            db.add(job)
            db.commit()
            db.refresh(job)

        # finished processing: mark completed
        job.status = "completed"
        job.processed = processed
        job.valid = valid
        job.invalid = invalid
        db.add(job)
        db.commit()
        db.refresh(job)

        # finalize: refunds, upload, webhook
        try:
            finalize_job_and_refund(db, job, estimated_cost, actual_count=total)
        except Exception:
            logger.exception("finalize_job_and_refund failed for %s", job.job_id)

    except KeyboardInterrupt:
        logger.warning("Bulk job cancelled by KeyboardInterrupt: %s", job_id)
        try:
            if job:
                job.status = "cancelled"
                db.add(job)
                db.commit()
        except Exception:
            pass
    except Exception as e:
        logger.exception("bulk job processor failed: %s", e)
        try:
            if job:
                job.status = "failed"
                job.error_message = str(e)
                db.add(job)
                db.commit()
        except Exception:
            pass
    finally:
        # stop writer thread gracefully
        try:
            if writer_q:
                # send sentinel
                try:
                    writer_q.put(None, timeout=2)
                except Exception:
                    # if queue full or blocked, ignore
                    pass
                # wait for queue to flush
                try:
                    writer_q.join()
                except Exception:
                    pass
            if writer_thread:
                writer_thread.stop()
                writer_thread.join(timeout=5)
        except Exception:
            pass

        # close DB
        try:
            db.close()
        except Exception:
            pass

        logger.info("Bulk job finished cleanup for %s", job_id)
