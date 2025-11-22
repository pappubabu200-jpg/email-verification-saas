# backend/app/workers/bulk_tasks.py
import io
import csv
import json
import os
import logging
from decimal import Decimal, ROUND_HALF_UP
from backend.app.celery_app import celery_app
from backend.app.db import SessionLocal
from backend.app.models.bulk_job import BulkJob
from backend.app.services.verification_engine import verify_email_sync
from backend.app.services.minio_client import get_object_bytes, put_bytes, MINIO_BUCKET, ensure_bucket
from backend.app.services.credits_service import capture_reservation, add_credits, reserve_and_deduct
from backend.app.services.credits_service import get_user_balance as _get_user_balance
from backend.app.services.billing_service import notify_user_low_balance if False else None
from backend.app.services.pricing_service import get_cost_for_key
from decimal import Decimal

logger = logging.getLogger(__name__)

def _dec(x) -> Decimal:
    return Decimal(str(x)).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)

@celery_app.task(bind=True, name="bulk.process_bulk_task", max_retries=3)
def process_bulk_task(self, job_id: str, estimated_cost: float = 0.0):
    """
    Worker: process a BulkJob. Steps:
     - load job row
     - load input file from MinIO (s3://bucket/...)
     - parse emails
     - verify each email (verify_email_sync)
     - write results JSON/CSV to MinIO
     - update BulkJob row (processed, valid, invalid, output_path, status)
     - finalize reservation: capture reservation -> record transaction OR refund policy
    """
    db = SessionLocal()
    try:
        job = db.query(BulkJob).filter(BulkJob.job_id == job_id).first()
        if not job:
            logger.error("process_bulk_task: job not found %s", job_id)
            return {"error": "job_not_found"}

        # load input bytes (support s3:// and local path)
        content = None
        if job.input_path and str(job.input_path).startswith("s3://"):
            # parse object path
            # input_path is s3://bucket/inputs/...
            try:
                # strip prefix
                parts = job.input_path.replace("s3://", "").split("/", 1)
                bucket = parts[0]
                obj = parts[1]
                data = get_object_bytes(obj)
                content = data
            except Exception as e:
                logger.exception("failed to read input from minio: %s", e)
                job.status = "error"
                job.error_message = "input_read_failed"
                db.add(job); db.commit()
                return {"error": "input_read_failed"}
        else:
            # try local file
            try:
                with open(job.input_path, "rb") as fh:
                    content = fh.read()
            except Exception as e:
                logger.exception("failed to read input file: %s", e)
                job.status = "error"
                job.error_message = "input_read_failed"
                db.add(job); db.commit()
                return {"error": "input_read_failed"}

        # parse emails from content (similar to API)
        filename = getattr(job, "input_path", "").split("/")[-1] or "upload"
        emails = []
        try:
            if filename.lower().endswith(".zip"):
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
            elif filename.lower().endswith((".csv", ".txt")):
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
            logger.exception("parse input failed: %s", e)
            job.status = "error"
            job.error_message = "parse_failed"
            db.add(job); db.commit()
            return {"error": "parse_failed"}

        # dedupe
        unique = list(dict.fromkeys([e.lower().strip() for e in emails if "@" in e]))
        total = len(unique)
        processed = 0
        valid = 0
        invalid = 0

        results = []
        # run verification for each email
        for e in unique:
            try:
                r = verify_email_sync(e, user_id=job.user_id)
                results.append({"email": e, "result": r})
                processed += 1
                if r.get("status") == "valid":
                    valid += 1
                else:
                    invalid += 1
            except Exception as ex:
                results.append({"email": e, "error": "verify_failed"})
                processed += 1
                invalid += 1

        # write results to MinIO as JSON and CSV
        ensure_bucket()
        out_json_obj = f"{OUTPUT_PREFIX}/{job.job_id}.json"
        out_csv_obj = f"{OUTPUT_PREFIX}/{job.job_id}.csv"

        json_bytes = json.dumps({"job_id": job.job_id, "total": total, "processed": processed, "valid": valid, "invalid": invalid, "results_preview": results[:100]}, indent=2).encode("utf-8")
        csv_buffer = io.StringIO()
        writer = csv.writer(csv_buffer)
        writer.writerow(["email", "status", "risk_score", "raw"])
        for r in results:
            if "result" in r:
                rr = r["result"]
                writer.writerow([r["email"], rr.get("status"), rr.get("risk_score"), json.dumps(rr.get("details") or rr.get("raw") or {})])
            else:
                writer.writerow([r.get("email"), "error", "", "verify_failed"])

        try:
            json_path = put_bytes(out_json_obj, json_bytes, content_type="application/json")
            put_bytes(out_csv_obj, csv_buffer.getvalue().encode("utf-8"), content_type="text/csv")
        except Exception:
            logger.exception("writing outputs to minio failed")

        # finalize job row
        job.processed = processed
        job.valid = valid
        job.invalid = invalid
        job.output_path = f"s3://{MINIO_BUCKET}/{out_json_obj}"
        job.status = "finished"
        db.add(job)
        db.commit()

        # capture reservation or refund policy:
        # estimated_cost provided to task; compute actual cost = cost_per * processed_count
        try:
            cost_per = Decimal(str(get_cost_for_key("verify.bulk_per_email") or 0))
            actual_cost = (cost_per * Decimal(processed)).quantize(Decimal("0.000001"))
            estimated = Decimal(str(estimated_cost)) if (estimated_cost := getattr(job, "estimated_cost", None)) else Decimal("0")
            # If job row doesn't store estimated_cost, attempting to use arg not available here.
            # For safety, do not double-charge: attempt to capture reservation if system used reservation DB flow.
            # If you implemented reservations as CreditReservation rows, you should capture them here.
            # For now we rely on earlier reserve_and_deduct call that already deducted upfront.
        except Exception:
            pass

        return {"job_id": job.job_id, "processed": processed, "valid": valid, "invalid": invalid}

    except Exception as exc:
        logger.exception("unexpected worker failure: %s", exc)
        try:
            job.status = "error"
            job.error_message = "worker_failed"
            db.add(job); db.commit()
        except Exception:
            pass
        raise
    finally:
        db.close()

from backend.app.services.credits_service import capture_reservation_and_charge, release_reservation_by_job

# If you record reservation.job_id earlier when reserving, you can look it up:
# reservations = db.query(CreditReservation).filter(CreditReservation.job_id==job.job_id, CreditReservation.locked==True).all()
# For each res -> capture_reservation_and_charge(res.id)

# Example (append after job processed):
try:
    # find reservations for this job
    from backend.app.models.credit_reservation import CreditReservation
    reservations = db.query(CreditReservation).filter(CreditReservation.job_id==job.job_id, CreditReservation.locked==True).all()
    actual_cost = (Decimal(str(get_cost_for_key("verify.bulk_per_email") or 0)) * Decimal(processed)).quantize(Decimal("0.000001"))
    # If many reservations exist, capture needed amount across them — simple approach: capture each in turn up to actual_cost
    remain = actual_cost
    for r in reservations:
        if remain <= 0:
            # release remaining reservations
            release_reservation_by_job(job.job_id)
            break
        try:
            # if r.amount <= remain -> capture whole reservation
            capture_reservation_and_charge(r.id, type_="bulk_charge", reference=f"bulk:{job.job_id}")
            remain -= Decimal(r.amount)
        except Exception:
            # cannot capture (something off) -> leave unlocked and continue
            logger.exception("capture reservation %s failed", r.id)
    # if remain < 0 (shouldn't), leave as is — admin can reconcile
except Exception:
    logger.exception("reservation finalize failed for job %s", job.job_id)


