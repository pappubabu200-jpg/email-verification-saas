# backend/app/services/bulk_processor.py
"""
Async Bulk Processor

- Non-blocking where possible.
- Uses asyncio.to_thread() for legacy blocking helpers (CSV parsing, sync verifiers, storage).
- Uses async SQLAlchemy (async_session).
- Writes CSV results with aiofiles.
"""

import os
import csv
import asyncio
import logging
from decimal import Decimal, ROUND_HALF_UP
from typing import List, Optional, Callable, Any

import aiofiles

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db import async_session
from backend.app.models.bulk_job import BulkJob
from backend.app.models.verification_result import VerificationResult
from backend.app.config import settings

# Legacy sync helper imports (may be blocking) — will be used via to_thread if needed
try:
    from backend.app.services.verification_engine import verify_email_async
    HAVE_ASYNC_VERIFIER = True
except Exception:
    HAVE_ASYNC_VERIFIER = False

try:
    from backend.app.services.verification_engine import verify_email_sync
    HAVE_SYNC_VERIFIER = True
except Exception:
    HAVE_SYNC_VERIFIER = False

# Legacy sync helpers used via to_thread
try:
    from backend.app.services.pricing_service import get_cost_for_key
except Exception:
    def get_cost_for_key(key):
        return Decimal("0")

try:
    from backend.app.services.credits_service import add_credits
except Exception:
    async def add_credits(*args, **kwargs):
        raise RuntimeError("credits_service.add_credits not available")

try:
    from backend.app.services.webhook_sender import webhook_task
except Exception:
    webhook_task = None

try:
    from backend.app.services.storage_s3 import upload_file_local_or_s3
except Exception:
    upload_file_local_or_s3 = None

# domain backoff helpers (may be sync)
try:
    from backend.app.services.domain_backoff import (
        acquire_slot,
        release_slot,
        get_backoff_seconds,
        increase_backoff,
        clear_backoff,
    )
except Exception:
    # Provide no-op fallbacks if not present
    def acquire_slot(domain): return True
    def release_slot(domain): return True
    def get_backoff_seconds(domain): return 0
    def increase_backoff(domain): return None
    def clear_backoff(domain): return None

logger = logging.getLogger(__name__)

CHUNK_SIZE = int(getattr(settings, "BULK_CHUNK_SIZE", 200))
RESULTS_FOLDER = getattr(settings, "BULK_RESULTS_FOLDER", "/tmp/bulk_results")
os.makedirs(RESULTS_FOLDER, exist_ok=True)


def _dec(x) -> Decimal:
    return Decimal(str(x)).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)


# -------------------------
# File / CSV helpers (sync)
# -------------------------
def _read_emails_from_path_sync(path: str) -> List[str]:
    emails = []
    _, ext = os.path.splitext(path.lower())
    if ext in (".csv", ".txt"):
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
    # dedupe in order
    seen = set()
    out = []
    for e in emails:
        if e not in seen:
            seen.add(e)
            out.append(e)
    return out


async def read_emails_from_path(path: str) -> List[str]:
    return await asyncio.to_thread(_read_emails_from_path_sync, path)


async def write_results_header(path: str):
    async with aiofiles.open(path, "w", encoding="utf-8", newline="") as fh:
        # write header as CSV row
        await fh.write("email,status,risk_score,raw_json\n")


async def append_result(path: str, email: str, status: str, risk_score: Optional[Any], raw_json: str):
    # CSV-safe line: we will roughly escape quotes by doubling - for heavy CSV use, consider csv in to_thread
    # Use simple CSV safe quoting
    line = f'"{email}","{status}","{risk_score if risk_score is not None else ""}","{raw_json.replace(chr(34), chr(34)*2)}"\n'
    async with aiofiles.open(path, "a", encoding="utf-8", newline="") as fh:
        await fh.write(line)


# -------------------------
# Finalize job: refund & upload & webhook
# -------------------------
async def finalize_job_and_refund(db: AsyncSession, job: BulkJob, estimated_cost: Decimal, actual_count: int):
    per_cost = _dec(await asyncio.to_thread(get_cost_for_key, "verify.bulk_per_email") or 0)
    actual_cost = (per_cost * Decimal(actual_count)).quantize(Decimal("0.000001"))
    refund = (estimated_cost - actual_cost).quantize(Decimal("0.000001")) if estimated_cost > actual_cost else Decimal("0")
    if refund > 0:
        try:
            # add_credits is async in your stack
            await add_credits(job.user_id, refund, reference=f"{job.job_id}:refund_after_processing")
        except Exception:
            logger.exception("refund failed for job %s", job.job_id)

    # upload to S3 (if configured) — run in threadpool
    try:
        if job.output_path and job.output_path.startswith("/"):
            if upload_file_local_or_s3:
                remote_key = f"bulk_results/{os.path.basename(job.output_path)}"
                remote_url = await asyncio.to_thread(upload_file_local_or_s3, job.output_path, remote_key)
                if remote_url and remote_url != job.output_path:
                    job.output_path = remote_url
                    db.add(job)
                    await db.commit()
                    await db.refresh(job)
    except Exception:
        logger.exception("s3 upload in finalize failed")

    # send webhook (enqueue task)
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
            if webhook_task and hasattr(webhook_task, "delay"):
                # Celery-style enqueue in threadpool (non-blocking)
                await asyncio.to_thread(webhook_task.delay, job.webhook_url, payload)
            elif webhook_task:
                # If webhook_task is a coroutine function
                if asyncio.iscoroutinefunction(webhook_task):
                    await webhook_task(job.webhook_url, payload)
                else:
                    await asyncio.to_thread(webhook_task, job.webhook_url, payload)
        except Exception:
            logger.exception("webhook enqueue failed for %s", job.job_id)


# -------------------------
# Verifier helper (async or sync fallback)
# -------------------------
async def _call_verifier(email: str) -> dict:
    """
    Prefer async verifier if available, otherwise call legacy sync verifier in threadpool.
    Expected to return a dict with keys: status, risk_score, details/raw, rcpt_response_code (optional)
    """
    if HAVE_ASYNC_VERIFIER:
        try:
            return await verify_email_async(email)
        except Exception as e:
            logger.exception("async verifier failed for %s: %s", email, e)
            # fall through to sync verifier fallback
    if HAVE_SYNC_VERIFIER:
        return await asyncio.to_thread(verify_email_sync, email)
    # If no verifier available, return unknown
    logger.error("No verifier available")
    return {"status": "unknown", "details": "no_verifier"}


# -------------------------
# Chunk processing (async)
# -------------------------
async def process_chunk_async(emails_chunk: List[str], output_path: str):
    vcount = 0
    icount = 0
    pcount = 0

    # Use semaphore to control concurrency inside a chunk if desired
    sem = asyncio.Semaphore(int(getattr(settings, "BULK_CONCURRENCY_PER_CHUNK", 10)))

    async def _process_email(email: str):
        nonlocal vcount, icount, pcount

        domain = email.split("@", 1)[-1] if "@" in email else None

        # respect backoff (domain backoff may be sync; call in threadpool)
        backoff = await asyncio.to_thread(get_backoff_seconds, domain) if domain else 0
        if backoff and backoff > 0:
            await asyncio.sleep(min(backoff, 10))

        # acquire slot (may be sync)
        got = await asyncio.to_thread(acquire_slot, domain) if domain else True
        if not got:
            # wait short and retry once
            await asyncio.sleep(1)
            got = await asyncio.to_thread(acquire_slot, domain) if domain else True
            if not got:
                await append_result(output_path, email, "skipped_throttle", None, "domain_throttle")
                icount += 1
                pcount += 1
                return

        try:
            # run verifier (async or sync fallback)
            res = await _call_verifier(email)
            status = res.get("status", "unknown")
            risk = res.get("risk_score")
            raw = res.get("details") or res.get("raw") or str(res)
            await append_result(output_path, email, status, risk, str(raw))
            pcount += 1

            if status == "valid":
                vcount += 1
                # clear backoff (may be sync)
                try:
                    await asyncio.to_thread(clear_backoff, domain)
                except Exception:
                    pass
            else:
                icount += 1
                rc = res.get("rcpt_response_code")
                try:
                    if rc and 400 <= int(rc) < 500:
                        await asyncio.to_thread(increase_backoff, domain)
                except Exception:
                    pass

        except Exception as e:
            logger.exception("verify failed for %s: %s", email, e)
            await append_result(output_path, email, "error", None, str(e))
            pcount += 1
            icount += 1
            try:
                await asyncio.to_thread(increase_backoff, domain)
            except Exception:
                pass
        finally:
            try:
                await asyncio.to_thread(release_slot, domain)
            except Exception:
                pass

    # run all emails in chunk concurrently (bounded by semaphore)
    async def _bounded(email):
        async with sem:
            await _process_email(email)

    tasks = [asyncio.create_task(_bounded(e)) for e in emails_chunk]
    await asyncio.gather(*tasks)

    return vcount, icount, pcount


# -------------------------
# Main job processor (entrypoint)
# -------------------------
async def process_bulk_job(job_id: str, estimated_cost: Decimal):
    async with async_session() as db:
        # fetch job record
        q = await db.execute(select(BulkJob).where(BulkJob.job_id == job_id))
        job = q.scalar_one_or_none()
        if not job:
            logger.error("bulk job not found %s", job_id)
            return

        # set running
        job.status = "running"
        db.add(job)
        await db.commit()
        await db.refresh(job)

        # read emails async (from local disk or mounted path)
        emails = await read_emails_from_path(job.input_path)
        total = len(emails)
        job.total = total
        db.add(job)
        await db.commit()
        await db.refresh(job)

        # prepare output
        output_fname = f"{job.job_id}.results.csv"
        output_path = os.path.join(RESULTS_FOLDER, output_fname)
        await write_results_header(output_path)
        job.output_path = output_path
        db.add(job)
        await db.commit()
        await db.refresh(job)

        processed = 0
        valid = 0
        invalid = 0

        # iterate chunks
        for i in range(0, total, CHUNK_SIZE):
            chunk = emails[i:i + CHUNK_SIZE]
            try:
                v, ic, p = await process_chunk_async(chunk, output_path)
            except Exception as e:
                logger.exception("process_chunk failed: %s", e)
                v, ic, p = 0, len(chunk), len(chunk)

            processed += p
            valid += v
            invalid += ic

            # persist progress frequently
            job.processed = processed
            job.valid = valid
            job.invalid = invalid
            db.add(job)
            await db.commit()
            await db.refresh(job)

        # done
        job.status = "completed"
        db.add(job)
        await db.commit()
        await db.refresh(job)

        # finalize (refund, upload, webhook)
        try:
            await finalize_job_and_refund(db, job, estimated_cost, actual_count=total)
        except Exception:
            logger.exception("finalize_job failed for %s", job.job_id)
