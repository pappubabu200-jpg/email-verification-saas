# backend/app/workers/bulk_tasks.py

import io
import csv
import json
import os
import zipfile
import logging
from decimal import Decimal, ROUND_HALF_UP

from backend.app.celery_app import celery_app
from backend.app.db import SessionLocal
from backend.app.models.bulk_job import BulkJob
from backend.app.services.verification_engine import verify_email_sync
from backend.app.services.minio_client import get_object_bytes, put_bytes, MINIO_BUCKET, ensure_bucket
from backend.app.services.credits_service import capture_reservation, get_user_balance
from backend.app.services.team_billing_service import capture_reservation_and_charge, release_reservation_by_job
from backend.app.services.pricing_service import get_cost_for_key
from backend.app.models.credit_reservation import CreditReservation

logger = logging.getLogger(__name__)

OUTPUT_PREFIX = "outputs/bulk"

def _dec(x) -> Decimal:
    return Decimal(str(x)).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)

@celery_app.task(bind=True, name="bulk.process_bulk_task", max_retries=3)
def process_bulk_task(self, job_id: str, estimated_cost: float = 0.0):
    """
    Worker: process a BulkJob. Steps:
    
    - load job row
    - load input file from MinIO (s3://bucket/...) or disk
    - parse emails
    - verify each email (verify_email_sync)
    - write results JSON/CSV to MinIO
    - update BulkJob row (processed, valid, invalid, output_path, status)
    - finalize reservation(s): capture/reserve or refund policy
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
            try:
                # parse object path
                parts = job.input_path.replace("s3://", "").split("/", 1)
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
            try:
                with open(job.input_path, "rb") as fh:
                    content = fh.read()
            except Exception as e:
                logger.exception("failed to read input file: %s", e)
                job.status = "error"
                job.error_message = "input_read_failed"
                db.add(job); db.commit()
                return {"error": "input_read_failed"}

        # parse emails
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

        unique = list(dict.fromkeys([e.lower().strip() for e in emails if "@" in e]))
        total = len(unique)
        processed = 0
        valid = 0
        invalid = 0
        results = []

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

        # write results to MinIO
        ensure_bucket()
        out_json_obj = f"{OUTPUT_PREFIX}/{job.job_id}.json"
        out_csv_obj = f"{OUTPUT_PREFIX}/{job.job_id}.csv"
        json_bytes = json.dumps({
            "job_id": job.job_id,
            "total": total,
            "processed": processed,
            "valid": valid,
            "invalid": invalid,
            "results_preview": results[:100]
        }, indent=2).encode("utf-8")

        csv_buffer = io.StringIO()
        writer = csv.writer(csv_buffer)
        writer.writerow(["email", "status", "risk_score", "raw"])
        for r in results:
            if "result" in r:
                rr = r["result"]
                writer.writerow([
                    r["email"], 
                    rr.get("status"), 
                    rr.get("risk_score"),
                    json.dumps(rr.get("details") or rr.get("raw") or {})
                ])
            else:
                writer.writerow([r.get("email"), "error", "", "verify_failed"])
        try:
            put_bytes(out_json_obj, json_bytes, content_type="application/json")
            put_bytes(out_csv_obj, csv_buffer.getvalue().encode("utf-8"), content_type="text/csv")
        except Exception:
            logger.exception("writing outputs to minio failed")

        # update job row
        job.processed = processed
        job.valid = valid
        job.invalid = invalid
        job.output_path = f"s3://{MINIO_BUCKET}/{out_json_obj}"
        job.status = "finished"
        db.add(job)
        db.commit()

        # finalize reservations: capture or release depending on team/user
        try:
            reservations = db.query(CreditReservation).filter(
                CreditReservation.job_id == job.job_id,
                CreditReservation.locked == True
            ).all()
            total_processed = Decimal(processed)
            cost_per = Decimal(str(get_cost_for_key("verify.bulk_per_email") or 0))
            actual_cost = (cost_per * total_processed).quantize(Decimal("0.000001"))
            remain = actual_cost

            for r in reservations:
                if getattr(r, "team_id", None):
                    try:
                        capture_res = capture_reservation_and_charge(
                            r.id, type_="bulk_charge", reference=f"bulk:{job.job_id}"
                        )
                        remain -= Decimal(r.amount)
                    except Exception:
                        logger.exception("capture team reservation failed %s", r.id)
                else:
                    try:
                        capture_res = capture_reservation(
                            r.id, type_="bulk_charge", reference=f"bulk:{job.job_id}"
                        )
                        remain -= Decimal(r.amount)
                    except Exception:
                        logger.exception("capture user reservation failed %s", r.id)
            if remain > 0:
                try:
                    from backend.app.services.credits_service import add_credits as user_add_credits
                    user_add_credits(job.user_id, remain, reference=f"{job.job_id}:auto_refund_remaining")
                except Exception:
                    logger.exception("auto refund remaining failed for %s remain=%s", job.job_id, remain)
        except Exception:
            logger.exception("reservation finalize failed for job %s", job.job_id)
        return {
            "job_id": job.job_id,
            "processed": processed,
            "valid": valid,
            "invalid": invalid
        }
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

# after processing job and writing outputs — find reservations by job_id
from backend.app.models.credit_reservation import CreditReservation
from backend.app.services.team_billing_service import capture_team_reservation_and_charge
from backend.app.services.credits_service import capture_reservation_and_charge

# fetch reservations for this job
reservations = db.query(CreditReservation).filter(CreditReservation.job_id==job.job_id, CreditReservation.locked==True).all()
actual_cost = (Decimal(str(get_cost_for_key("verify.bulk_per_email") or 0)) * Decimal(processed)).quantize(Decimal("0.000001"))
# simple approach: capture reservations one by one up to actual_cost
remain = actual_cost
for r in reservations:
    if remain <= 0:
        # release any remaining reservations for this job
        release_reservation_by_job(job.job_id)
        break
    try:
        if r.reference and isinstance(r.reference, str) and r.reference.startswith("team:"):
            # extract team id
            try:
                team_id = int(r.reference.split("team:")[1].split(":")[0])
            except Exception:
                # fallback if format differs
                team_id = None
            if team_id:
                capture_team_reservation_and_charge(db, r.id, team_id=team_id, type_="bulk.charge", reference=f"bulk:{job.job_id}")
                remain -= Decimal(str(r.amount))
                continue
        # else capture user reservation
        capture_reservation_and_charge(db, r.id, type_="bulk.charge", reference=f"bulk:{job.job_id}")
        remain -= Decimal(str(r.amount))
    except Exception:
        logger.exception("capture reservation %s failed", r.id)
# if remain > 0 => admin reconciliation may be needed (or leave as is)


