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

# ⭐ WebSocket Managers
from backend.app.services.bulk_ws_manager import bulk_ws_manager
from backend.app.services.verification_ws_manager import verification_ws

import asyncio

logger = logging.getLogger(__name__)

OUTPUT_PREFIX = "outputs/bulk"


def _dec(x):
    """Convert to Decimal with 6 decimal places precision"""
    return Decimal(str(x)).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)


@celery_app.task(bind=True, name="bulk.process_bulk_task", max_retries=2)
def process_bulk_task(self, job_id: str):
    logger.info(f"[Worker] Starting job {job_id}")

    db = SessionLocal()
    try:
        job = db.query(BulkJob).filter(BulkJob.job_id == job_id).first()
        if not job:
            logger.error(f"Job not found: {job_id}")

            # WS broadcast (Bulk + User)
            try:
                asyncio.run(bulk_ws_manager.broadcast(job_id, {
                    "event": "failed",
                    "error": "job_not_found"
                }))
                asyncio.run(verification_ws.push(job.user_id, {
                    "event": "bulk_failed",
                    "job_id": job_id,
                    "error": "job_not_found"
                }))
            except:
                pass

            return {"error": "job_not_found"}

        # --------------------------------------------------------
        # 1) Load input file
        # --------------------------------------------------------
        try:
            if str(job.input_path).startswith("s3://"):
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
            db.commit()

            # WS failure broadcast
            asyncio.run(bulk_ws_manager.broadcast(job_id, {
                "event": "failed",
                "error": "input_read_failed"
            }))
            asyncio.run(verification_ws.push(job.user_id, {
                "event": "bulk_failed",
                "job_id": job_id,
                "error": "input_read_failed"
            }))
            return {"error": "input_read_failed"}

        # --------------------------------------------------------
        # 2) Parse file
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
                                if "@" in col.strip():
                                    emails.append(col.strip())
                                    break
                    else:
                        for line in raw.splitlines():
                            if "@" in line.strip():
                                emails.append(line.strip())

            elif filename.endswith(".csv"):
                raw = content.decode("utf-8", errors="ignore")
                reader = csv.reader(io.StringIO(raw))
                for row in reader:
                    for col in row:
                        if "@" in col.strip():
                            emails.append(col.strip())
                            break
            else:
                raw = content.decode("utf-8", errors="ignore")
                for line in raw.splitlines():
                    if "@" in line.strip():
                        emails.append(line.strip())

        except Exception as e:
            logger.exception("Parse failed: %s", e)
            job.status = "error"
            job.error_message = "parse_failed"
            db.commit()

            asyncio.run(bulk_ws_manager.broadcast(job_id, {
                "event": "failed",
                "error": "parse_failed"
            }))
            asyncio.run(verification_ws.push(job.user_id, {
                "event": "bulk_failed",
                "job_id": job_id,
                "error": "parse_failed"
            }))

            return {"error": "parse_failed"}

        # Deduplicate emails
        emails = list(dict.fromkeys([e.lower() for e in emails if "@" in e]))
        total = len(emails)

        if total == 0:
            job.status = "error"
            job.error_message = "no_valid_emails"
            db.commit()

            asyncio.run(bulk_ws_manager.broadcast(job_id, {
                "event": "failed",
                "error": "no_valid_emails"
            }))
            asyncio.run(verification_ws.push(job.user_id, {
                "event": "bulk_failed",
                "job_id": job_id,
                "error": "no_valid_emails"
            }))
            return {"error": "no_valid_emails"}

        logger.info(f"[Worker] Job {job_id}: Found {total} emails")

        # --------------------------------------------------------
        # 3) Verification Loop (WebSocket updates here)
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
                results.append({"email": e, "error": "verify_failed"})
                processed += 1
                invalid += 1

            # ⭐ WS PROGRESS
            update_payload = {
                "event": "progress",
                "processed": processed,
                "total": total,
                "stats": {
                    "valid": valid,
                    "invalid": invalid,
                    "remaining": total - processed
                }
            }

            asyncio.run(bulk_ws_manager.broadcast(job_id, update_payload))
            asyncio.run(verification_ws.push(job.user_id, {
                "event": "bulk_progress",
                "job_id": job.job_id,
                **update_payload
            }))

        # --------------------------------------------------------
        # 4) Save outputs to MinIO
        # --------------------------------------------------------
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
                        rr.get("status", ""),
                        rr.get("risk_score", ""),
                        json.dumps(rr.get("details", {}))
                    ])
                else:
                    writer.writerow([r["email"], "error", "", "verify_failed"])

            put_bytes(csv_obj, csv_buf.getvalue().encode("utf-8"), content_type="text/csv")

        except Exception as e:
            logger.exception("Failed saving outputs: %s", e)

        # --------------------------------------------------------
        # 5) Update DB
        # --------------------------------------------------------
        job.processed = processed
        job.valid = valid
        job.invalid = invalid
        job.status = "finished"
        job.output_path = f"s3://{MINIO_BUCKET}/{json_obj}"
        db.commit()

        # --------------------------------------------------------
        # 6) WS COMPLETED EVENT (Bulk + User)
        # --------------------------------------------------------
        completed_payload = {
            "event": "completed",
            "processed": processed,
            "total": total,
            "stats": {"valid": valid, "invalid": invalid}
        }

        asyncio.run(bulk_ws_manager.broadcast(job_id, completed_payload))
        asyncio.run(verification_ws.push(job.user_id, {
            "event": "bulk_completed",
            "job_id": job.job_id,
            **completed_payload
        }))

        return {
            "job_id": job.job_id,
            "processed": processed,
            "valid": valid,
            "invalid": invalid
        }

    except Exception as exc:
        logger.exception(f"[Worker] Failure for job {job_id}: {exc}")

        try:
            job = db.query(BulkJob).filter(BulkJob.job_id == job_id).first()
            if job:
                job.status = "error"
                job.error_message = "worker_failed"
                db.commit()

            asyncio.run(bulk_ws_manager.broadcast(job_id, {
                "event": "failed",
                "error": "worker_failed"
            }))
            asyncio.run(verification_ws.push(job.user_id, {
                "event": "bulk_failed",
                "job_id": job_id,
                "error": "processing_error"
            }))

        except:
            pass

        raise

    finally:
        db.close()
