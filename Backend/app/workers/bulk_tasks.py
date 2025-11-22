# backend/app/workers/bulk_tasks.py

import io
import csv
import json
import uuid
import logging
from decimal import Decimal
from celery import shared_task

from backend.app.db import SessionLocal
from backend.app.models.bulk_job import BulkJob
from backend.app.services.verification_engine import verify_email_sync
from backend.app.services.credits_service import add_credits
from backend.app.services.team_billing_service import add_team_credits
from backend.app.services.pricing_service import get_cost_for_key
from backend.app.services.webhook_sender import webhook_task
from backend.app.services.minio_client import client, MINIO_BUCKET

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3)
def process_bulk_task(self, job_id: str, estimated_cost: float):
    """
    MinIO-based Bulk Verification Worker
    -----------------------------------
    Steps:
      1) Load job
      2) Download file from MinIO
      3) Extract emails
      4) Verify each email
      5) Upload results to MinIO
      6) Calculate refunds
      7) Update DB
      8) Trigger webhook
    """

    db = SessionLocal()
    try:
        # Load job
        job = db.query(BulkJob).filter(BulkJob.job_id == job_id).first()
        if not job:
            logger.error("bulk job not found: %s", job_id)
            return False

        job.status = "processing"
        db.commit()

        # ----------------------------------------
        # STEP 1: Download input file from MinIO
        # ----------------------------------------
        object_key = job.input_path.replace(f"s3://{MINIO_BUCKET}/", "")
        obj = client.get_object(MINIO_BUCKET, object_key)
        raw_bytes = obj.read()
        text = raw_bytes.decode("utf-8", errors="ignore")

        emails = [line.strip() for line in text.splitlines() if "@" in line]
        emails = list(dict.fromkeys(emails))
        total = len(emails)

        processed = 0
        valid = 0
        invalid = 0
        results = []

        # ----------------------------------------
        # STEP 2: Process Emails
        # ----------------------------------------
        for email in emails:
            try:
                r = verify_email_sync(email, user_id=job.user_id)
                results.append({"email": email, "result": r})

                if r.get("status") == "valid":
                    valid += 1
                else:
                    invalid += 1

            except Exception:
                results.append({"email": email, "error": "verify_failed"})
                invalid += 1

            processed += 1
            job.processed = processed
            job.valid = valid
            job.invalid = invalid
            db.commit()

        # ----------------------------------------
        # STEP 3: Calculate Refunds
        # ----------------------------------------
        refund_amount = Decimal("0")

        if total > 0 and (invalid / total) >= 0.5:
            refund_amount = Decimal(str(estimated_cost)) * Decimal("0.4")

            if job.team_id:
                add_team_credits(job.team_id, refund_amount, reference=f"{job_id}:refund")
            else:
                add_credits(job.user_id, refund_amount, reference=f"{job_id}:refund")

        # ----------------------------------------
        # STEP 4: Upload Results to MinIO
        # ----------------------------------------
        out_key = f"bulk-results/{job.user_id}-{uuid.uuid4().hex}.csv"

        csv_buf = io.StringIO()
        writer = csv.writer(csv_buf)
        writer.writerow(["email", "status", "risk_score", "raw"])

        for r in results:
            if "result" in r:
                rr = r["result"]
                writer.writerow([
                    r["email"],
                    rr.get("status"),
                    rr.get("risk_score"),
                    json.dumps(rr),
                ])
            else:
                writer.writerow([r["email"], "error", "", "verify_failed"])

        out_bytes = csv_buf.getvalue().encode("utf-8")
        client.put_object(
            MINIO_BUCKET,
            out_key,
            io.BytesIO(out_bytes),
            length=len(out_bytes),
            content_type="text/csv",
        )

        job.output_path = f"s3://{MINIO_BUCKET}/{out_key}"
        job.status = "completed"
        db.commit()

        # ----------------------------------------
        # STEP 5: Webhook Notification
        # ----------------------------------------
        if job.webhook_url:
            payload = {
                "event": "bulk.completed",
                "job_id": job.job_id,
                "total": total,
                "valid": valid,
                "invalid": invalid,
                "output_path": job.output_path,
                "refund": float(refund_amount),
            }
            webhook_task.delay(job.webhook_url, payload)

        return True

    except Exception as e:
        logger.exception("bulk worker failed: %s", e)
        try:
            job.status = "failed"
            job.error_message = str(e)
            db.commit()
        except:
            pass
        raise self.retry(countdown=60)

    finally:
        db.close()
