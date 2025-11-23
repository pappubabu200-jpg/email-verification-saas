# backend/app/workers/bulk_tasks.py

import io
import csv
import json
import logging
import zipfile
from decimal import Decimal, ROUND_HALF_UP

from backend.app.celery_app import celery_app
from backend.app.db import SessionLocal
from backend.app.models.bulk_job import BulkJob
from backend.app.models.credit_reservation import CreditReservation

from backend.app.services.verification_engine import verify_email_sync
from backend.app.services.minio_client import (
    get_object_bytes,
    put_bytes,
    ensure_bucket,
    MINIO_BUCKET
)

from backend.app.services.pricing_service import get_cost_for_key
from backend.app.services.credits_service import (
    capture_reservation,
    release_reservation_by_job
)
from backend.app.services.team_billing_service import (
    capture_reservation_and_charge,
    release_reservation_by_job as release_team_reservation
)

logger = logging.getLogger(__name__)

OUTPUT_PREFIX = "outputs/bulk"


def _dec(x):
    """Convert to Decimal with 6 decimal places precision"""
    return Decimal(str(x)).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)


@celery_app.task(bind=True, name="bulk.process_bulk_task", max_retries=2)
def process_bulk_task(self, job_id: str):
    """
    Bulk job processor:
    - Load job + fetch file (local or minio)
    - Parse emails
    - Verify each email
    - Save results to MinIO (JSON + CSV)
    - Charge/capture reservation EXACT to usage
    - Release unused reservations
    """
    logger.info(f"[Worker] Starting job {job_id}")

    db = SessionLocal()
    try:
        job = db.query(BulkJob).filter(BulkJob.job_id == job_id).first()
        if not job:
            logger.error(f"Job not found: {job_id}")
            return {"error": "job_not_found"}

        # --------------------------------------------------------
        # 1) LOAD INPUT FILE (minio or disk)
        # --------------------------------------------------------
        try:
            if str(job.input_path).startswith("s3://"):
                # s3://bucket/object
                s = job.input_path.replace("s3://", "").split("/", 1)
                obj = s[1]
                content = get_object_bytes(obj)
            else:
                with open(job.input_path, "rb") as fh:
                    content = fh.read()
        except Exception as e:
            logger.exception("Input read failed: %s", e)
            job.status = "error"
            job.error_message = "input_read_failed"
            db.add(job)
            db.commit()
            return {"error": "input_read_failed"}

        # --------------------------------------------------------
        # 2) PARSE EMAILS
        # --------------------------------------------------------
        emails = []
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
                                col_stripped = col.strip()
                                if "@" in col_stripped:
                                    emails.append(col_stripped)
                                    break
                    else:
                        for line in raw.splitlines():
                            line_stripped = line.strip()
                            if "@" in line_stripped:
                                emails.append(line_stripped)
            elif filename.endswith(".csv"):
                raw = content.decode("utf-8", errors="ignore")
                reader = csv.reader(io.StringIO(raw))
                for row in reader:
                    for col in row:
                        col_stripped = col.strip()
                        if "@" in col_stripped:
                            emails.append(col_stripped)
                            break
            else:
                raw = content.decode("utf-8", errors="ignore")
                for line in raw.splitlines():
                    line_stripped = line.strip()
                    if "@" in line_stripped:
                        emails.append(line_stripped)
        except Exception as e:
            logger.exception("Parse failed: %s", e)
            job.status = "error"
            job.error_message = "parse_failed"
            db.add(job)
            db.commit()
            return {"error": "parse_failed"}

        # Deduplicate emails (case-insensitive)
        emails = list(dict.fromkeys([e.lower() for e in emails if "@" in e]))
        total = len(emails)

        if total == 0:
            job.status = "error"
            job.error_message = "no_valid_emails"
            db.add(job)
            db.commit()
            return {"error": "no_valid_emails"}

        logger.info(f"[Worker] Job {job_id}: Found {total} unique emails")

        # --------------------------------------------------------
        # 3) VERIFY EMAILS
        # --------------------------------------------------------
        processed = 0
        valid = 0
        invalid = 0
        results = []

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
                logger.exception(f"Verification failed for {e}: {ex}")
                results.append({"email": e, "error": "verify_failed"})
                processed += 1
                invalid += 1

        # --------------------------------------------------------
        # 4) SAVE OUTPUTS (MinIO)
        # --------------------------------------------------------
        try:
            ensure_bucket()

            json_obj = f"{OUTPUT_PREFIX}/{job.job_id}.json"
            csv_obj = f"{OUTPUT_PREFIX}/{job.job_id}.csv"

            # JSON output
            json_bytes = json.dumps({
                "job_id": job.job_id,
                "total": total,
                "processed": processed,
                "valid": valid,
                "invalid": invalid,
                "results_preview": results[:100]
            }, indent=2).encode("utf-8")

            put_bytes(json_obj, json_bytes, content_type="application/json")

            # CSV output
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

            logger.info(f"[Worker] Job {job_id}: Outputs saved to MinIO")

        except Exception as e:
            logger.exception(f"Failed to save outputs: {e}")
            # Continue even if output saving fails

        # --------------------------------------------------------
        # 5) UPDATE JOB
        # --------------------------------------------------------
        job.processed = processed
        job.valid = valid
        job.invalid = invalid
        job.output_path = f"s3://{MINIO_BUCKET}/{json_obj}"
        job.status = "finished"
        db.add(job)
        db.commit()

        # --------------------------------------------------------
        # 6) RESERVATION FINALIZATION
        # --------------------------------------------------------
        try:
            # Find all reservations linked to this job
            reservations = db.query(CreditReservation).filter(
                CreditReservation.job_id == job.job_id,
                CreditReservation.locked == True
            ).all()

            cost_per = _dec(get_cost_for_key("verify.bulk_per_email") or 0)
            actual_cost = (cost_per * Decimal(processed)).quantize(Decimal("0.000001"))

            logger.info(f"[Worker] Job {job_id}: Actual cost = {actual_cost}, Reservations = {len(reservations)}")

            remaining_cost = actual_cost

            for res in reservations:
                if remaining_cost <= 0:
                    # Release unused reservations
                    try:
                        if res.reference and str(res.reference).startswith("team:"):
                            release_team_reservation(job.job_id)
                        else:
                            res.locked = False
                            db.add(res)
                    except Exception as e:
                        logger.exception(f"Failed to release reservation {res.id}: {e}")
                    continue

                res_amount = _dec(res.amount)

                try:
                    # Team reservation
                    if res.reference and str(res.reference).startswith("team:"):
                        parts = res.reference.split(":")
                        if len(parts) >= 2:
                            team_id = int(parts[1])
                            capture_reservation_and_charge(
                                res.id,
                                type_="bulk_charge",
                                reference=f"bulk:{job.job_id}"
                            )
                            remaining_cost -= res_amount
                            logger.info(f"[Worker] Captured team reservation {res.id} for team {team_id}")
                        else:
                            logger.error(f"Invalid team reference format: {res.reference}")

                    # User reservation
                    else:
                        capture_reservation(
                            db,
                            res.id,
                            type_="bulk_charge",
                            reference=f"bulk:{job.job_id}"
                        )
                        remaining_cost -= res_amount
                        logger.info(f"[Worker] Captured user reservation {res.id}")

                except Exception as e:
                    logger.exception(f"Reservation capture failed for {res.id}: {e}")
                    # Mark as unlocked on failure
                    res.locked = False
                    db.add(res)

            db.commit()

            if remaining_cost > 0:
                logger.warning(
                    f"[Worker] Job {job_id}: Remaining cost {remaining_cost} not covered by reservations"
                )

        except Exception as e:
            logger.exception(f"Reservation finalization failed for job {job_id}: {e}")

        logger.info(f"[Worker] Finished job {job_id}: {processed} processed, {valid} valid, {invalid} invalid")

        return {
            "job_id": job.job_id,
            "processed": processed,
            "valid": valid,
            "invalid": invalid
        }

    except Exception as exc:
        logger.exception(f"Unexpected worker failure for job {job_id}: {exc}")
        try:
            job = db.query(BulkJob).filter(BulkJob.job_id == job_id).first()
            if job:
                job.status = "error"
                job.error_message = "worker_failed"
                db.add(job)
                db.commit()
        except Exception:
            pass
        raise

    finally:
        db.close()
