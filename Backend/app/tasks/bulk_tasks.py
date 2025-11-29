# backend/app/tasks/bulk_tasks.py
"""
Celery task: process a bulk verification job (single file).
Publishes realtime updates via ws_broker (Redis PubSub).

Channels published:
- f"bulk:{job_id}"                 -> job-specific channel (progress/completed/failed)
- f"user:{user_id}:verification"  -> user-level notifications (bulk_progress, bulk_completed, bulk_failed)

Assumptions:
- ws_broker.publish(channel: str, payload: dict) is an async function
- MinIO helpers: ensure_bucket(), put_bytes(object_name, bytes, content_type)
- verify_email_sync(email, user_id=...) exists and returns dict with 'status' and optional details
- capture_reservation / capture_reservation_and_charge exist to finalize charging
- trigger_webhook.delay(event_name, payload, team_id=...) exists for webhooks
- SessionLocal returns a SQLAlchemy Session (sync)
"""

from __future__ import annotations

import io
import csv
import json
import logging
import zipfile
import asyncio
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional, Dict, Any, List

from backend.app.celery_app import celery_app
from backend.app.db import SessionLocal
from backend.app.models.bulk_job import BulkJob
from backend.app.models.credit_reservation import CreditReservation

from backend.app.services.verification_engine import verify_email_sync
from backend.app.services.minio_client import (
    get_object_bytes,
    put_bytes,
    ensure_bucket,
    MINIO_BUCKET,
)
from backend.app.services.pricing_service import get_cost_for_key
from backend.app.services.credits_service import (
    capture_reservation,
    release_reservation_by_job,
)
from backend.app.services.team_billing_service import (
    capture_reservation_and_charge,
    release_reservation_by_job as release_team_reservation,
)

# Redis PubSub broker (async)
from backend.app.services.ws_broker import ws_broker

# Optional webhook triggering (celery-friendly)
try:
    from backend.app.services.webhook_service import trigger_webhook
except Exception:
    trigger_webhook = None  # best-effort

logger = logging.getLogger(__name__)

OUTPUT_PREFIX = "outputs/bulk"


def _dec(x) -> Decimal:
    """Convert to Decimal with 6 decimal places precision"""
    return Decimal(str(x)).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)


# ---------------------------
# Pub helpers (sync wrappers)
# ---------------------------
def _publish(channel: str, payload: Dict[str, Any]):
    """Sync wrapper to call async ws_broker.publish"""
    try:
        asyncio.run(ws_broker.publish(channel, payload))
    except Exception:
        logger.debug("ws_broker.publish failed for channel=%s payload=%s", channel, payload, exc_info=True)


def _publish_progress(job_id: str, processed: int, total: int, valid: int, invalid: int, user_id: Optional[int]):
    payload = {
        "event": "progress",
        "job_id": job_id,
        "processed": processed,
        "total": total,
        "stats": {"valid": valid, "invalid": invalid, "remaining": max(0, total - processed)},
    }
    # publish to job channel
    _publish(f"bulk:{job_id}", payload)

    # publish user-level event
    if user_id:
        user_payload = {**payload, "event": "bulk_progress", "user_id": user_id}
        _publish(f"user:{user_id}:verification", user_payload)


def _publish_completed(job_id: str, processed: int, total: int, valid: int, invalid: int, user_id: Optional[int]):
    payload = {
        "event": "completed",
        "job_id": job_id,
        "processed": processed,
        "total": total,
        "stats": {"valid": valid, "invalid": invalid},
    }
    _publish(f"bulk:{job_id}", payload)
    if user_id:
        user_payload = {**payload, "event": "bulk_completed", "user_id": user_id}
        _publish(f"user:{user_id}:verification", user_payload)


def _publish_failed(job_id: str, error: str, user_id: Optional[int]):
    payload = {"event": "failed", "job_id": job_id, "error": error}
    _publish(f"bulk:{job_id}", payload)
    if user_id:
        user_payload = {"event": "bulk_failed", "job_id": job_id, "error": error, "user_id": user_id}
        _publish(f"user:{user_id}:verification", user_payload)


# ---------------------------
# Celery Task (full processor)
# ---------------------------
@celery_app.task(
    bind=True,
    name="backend.app.tasks.bulk_tasks.process_bulk_job_task",
    acks_late=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_kwargs={"max_retries": 3},
)
def process_bulk_job_task(self, job_id: str, estimated_cost: float = 0.0) -> Dict[str, Any]:
    """
    Celery task that processes a bulk job end-to-end and publishes progress via Redis PubSub.
    """
    logger.info("Celery: starting bulk job %s", job_id)
    db = SessionLocal()

    try:
        job: Optional[BulkJob] = db.query(BulkJob).filter(BulkJob.job_id == job_id).first()
        if not job:
            logger.error("Job not found: %s", job_id)
            _publish_failed(job_id, "job_not_found", None)
            return {"ok": False, "reason": "job_not_found", "job_id": job_id}

        user_id = getattr(job, "user_id", None)

        # idempotency/resume guard
        if getattr(job, "status", "") in ("running", "finished", "completed"):
            logger.info("Job %s already %s", job_id, job.status)
            return {"ok": True, "info": f"already_{job.status}", "job_id": job_id}

        # mark running
        job.status = "running"
        db.add(job)
        db.commit()
        db.refresh(job)

        # 1) Load file content
        try:
            if str(job.input_path).startswith("s3://"):
                s = job.input_path.replace("s3://", "").split("/", 1)
                obj = s[1]
                content = get_object_bytes(obj)
            else:
                with open(job.input_path, "rb") as fh:
                    content = fh.read()
        except Exception as e:
            logger.exception("Failed to read input for job %s", job_id)
            job.status = "failed"
            job.error_message = "input_read_failed"
            db.add(job)
            db.commit()
            _publish_failed(job_id, "input_read_failed", user_id)
            return {"ok": False, "reason": "input_read_failed"}

        # 2) Parse emails (csv / zip / plain)
        emails: List[str] = []
        filename = job.input_path.split("/")[-1].lower()
        try:
            if filename.endswith(".zip"):
                z = zipfile.ZipFile(io.BytesIO(content))
                for name in z.namelist():
                    if name.endswith("/") or name.startswith("__MACOSX"):
                        continue
                    raw = z.read(name).decode("utf-8", errors="ignore")
                    if name.lower().endswith(".csv"):
                        reader = csv.reader(io.StringIO(raw))
                        for row in reader:
                            for col in row:
                                col_str = col.strip()
                                if "@" in col_str:
                                    emails.append(col_str)
                                    break
                    else:
                        for line in raw.splitlines():
                            line_str = line.strip()
                            if "@" in line_str:
                                emails.append(line_str)
            elif filename.endswith(".csv"):
                raw = content.decode("utf-8", errors="ignore")
                reader = csv.reader(io.StringIO(raw))
                for row in reader:
                    for col in row:
                        col_str = col.strip()
                        if "@" in col_str:
                            emails.append(col_str)
                            break
            else:
                raw = content.decode("utf-8", errors="ignore")
                for line in raw.splitlines():
                    line_str = line.strip()
                    if "@" in line_str:
                        emails.append(line_str)
        except Exception as e:
            logger.exception("Parse failed for job %s", job_id)
            job.status = "failed"
            job.error_message = "parse_failed"
            db.add(job)
            db.commit()
            _publish_failed(job_id, "parse_failed", user_id)
            return {"ok": False, "reason": "parse_failed"}

        # dedupe case-insensitive
        emails = list(dict.fromkeys([e.lower() for e in emails if "@" in e]))
        total = len(emails)

        if total == 0:
            logger.warning("No valid emails for job %s", job_id)
            job.status = "failed"
            job.error_message = "no_valid_emails"
            db.add(job)
            db.commit()
            _publish_failed(job_id, "no_valid_emails", user_id)
            return {"ok": False, "reason": "no_valid_emails"}

        logger.info("Job %s: %d unique emails", job_id, total)

        # 3) Verification loop
        processed = 0
        valid = 0
        invalid = 0
        results: List[Dict[str, Any]] = []

        # initial publish (0%)
        _publish_progress(job_id, processed, total, valid, invalid, user_id)

        for e in emails:
            try:
                r = verify_email_sync(e, user_id=job.user_id)
                results.append({"email": e, "result": r})
                processed += 1
                if r.get("status") == "valid":
                    valid += 1
                else:
                    invalid += 1
            except Exception as ex:
                logger.exception("Verification error for %s in job %s", e, job_id)
                results.append({"email": e, "error": "verify_failed"})
                processed += 1
                invalid += 1

            # publish progress for each email (best-effort)
            try:
                _publish_progress(job_id, processed, total, valid, invalid, user_id)
            except Exception:
                logger.debug("Failed to publish progress for job %s", job_id, exc_info=True)

        # 4) Save outputs to MinIO (JSON + CSV)
        json_obj = None
        try:
            ensure_bucket()
            json_obj = f"{OUTPUT_PREFIX}/{job.job_id}.json"
            csv_obj = f"{OUTPUT_PREFIX}/{job.job_id}.csv"

            json_bytes = json.dumps({
                "job_id": job.job_id,
                "total": total,
                "processed": processed,
                "valid": valid,
                "invalid": invalid,
                "results_preview": results[:100]
            }, indent=2).encode("utf-8")

            put_bytes(json_obj, json_bytes, content_type="application/json")

            csv_buf = io.StringIO()
            writer = csv.writer(csv_buf)
            writer.writerow(["email", "status", "risk_score", "details"])

            for r in results:
                if "result" in r:
                    rr = r["result"]
                    writer.writerow([
                        r["email"],
                        rr.get("status", "unknown"),
                        rr.get("risk_score", ""),
                        json.dumps(rr.get("details", {}))
                    ])
                else:
                    writer.writerow([r["email"], "error", "", "verify_failed"])

            put_bytes(csv_obj, csv_buf.getvalue().encode("utf-8"), content_type="text/csv")

        except Exception:
            logger.exception("Failed to save outputs for job %s", job_id, exc_info=True)
            # continue — we still finish the job but note failure in logs

        # 5) Update job DB row & finalize reservations
        try:
            job.processed = processed
            job.valid = valid
            job.invalid = invalid
            if json_obj:
                job.output_path = f"s3://{MINIO_BUCKET}/{json_obj}"
            job.status = "finished"
            db.add(job)
            db.commit()
        except Exception:
            logger.exception("Failed to update job row for %s", job_id, exc_info=True)

        # finalize capture/release of reservations
        try:
            reservations = db.query(CreditReservation).filter(
                CreditReservation.job_id == job.job_id,
                CreditReservation.locked == True
            ).all()

            cost_per = _dec(get_cost_for_key("verify.bulk_per_email") or 0)
            actual_cost = (cost_per * Decimal(processed)).quantize(Decimal("0.000001"))
            remaining_cost = actual_cost

            for res in reservations:
                if remaining_cost <= 0:
                    # release unused reservations
                    try:
                        if res.reference and str(res.reference).startswith("team:"):
                            release_team_reservation(job.job_id)
                        else:
                            res.locked = False
                            db.add(res)
                    except Exception:
                        logger.exception("Failed to release reservation %s", getattr(res, "id", "<no-id>"))
                    continue

                res_amount = _dec(res.amount)
                try:
                    if res.reference and str(res.reference).startswith("team:"):
                        capture_reservation_and_charge(
                            res.id,
                            type_="bulk_charge",
                            reference=f"bulk:{job.job_id}"
                        )
                        remaining_cost -= res_amount
                    else:
                        capture_reservation(
                            db,
                            res.id,
                            type_="bulk_charge",
                            reference=f"bulk:{job.job_id}"
                        )
                        remaining_cost -= res_amount
                except Exception:
                    logger.exception("Reservation capture failed for %s", getattr(res, "id", "<no-id>"))
                    # mark unlocked to avoid stale lock
                    try:
                        res.locked = False
                        db.add(res)
                    except Exception:
                        pass

            db.commit()
            if remaining_cost > 0:
                logger.warning("Job %s: Remaining cost %s not covered by reservations", job.job_id, remaining_cost)
        except Exception:
            logger.exception("Reservation finalization error for %s", job_id, exc_info=True)

        # 6) Publish completed event
        try:
            _publish_completed(job_id, processed, total, valid, invalid, user_id)
        except Exception:
            logger.debug("Failed to publish completion for job %s", job_id, exc_info=True)

        # 7) Trigger webhook (best-effort)
        try:
            if trigger_webhook is not None:
                final_stats = {
                    "job_id": job.job_id,
                    "status": job.status,
                    "total": total,
                    "processed": processed,
                    "valid": valid,
                    "invalid": invalid,
                    "output_path": job.output_path if getattr(job, "output_path", None) else None,
                }
                # use celery delay for webhook to not block
                try:
                    trigger_webhook.delay("bulk_job.finished", final_stats, team_id=job.team_id or job.user_id)
                except Exception:
                    # fallback to calling directly (rare)
                    try:
                        trigger_webhook("bulk_job.finished", final_stats, team_id=job.team_id or job.user_id)
                    except Exception:
                        logger.debug("trigger_webhook call failed", exc_info=True)
        except Exception:
            logger.debug("Webhook invocation failed (ignored)", exc_info=True)

        logger.info("Celery: finished job %s processed=%s valid=%s invalid=%s", job_id, processed, valid, invalid)
        return {"ok": True, "job_id": job_id, "processed": processed, "valid": valid, "invalid": invalid}

    except Exception as exc:
        logger.exception("Unexpected worker failure for job %s: %s", job_id, exc)
        try:
            j = db.query(BulkJob).filter(BulkJob.job_id == job_id).first()
            if j:
                j.status = "failed"
                j.error_message = "worker_failed"
                db.add(j)
                db.commit()
            # publish failure event
            _publish_failed(job_id, "worker_failed", getattr(j, "user_id", None) if j else None)
        except Exception:
            logger.exception("Failed to mark job failure", exc_info=True)
        raise
    finally:
        try:
            db.close()
        except Exception:
            pass
