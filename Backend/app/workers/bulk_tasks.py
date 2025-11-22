# backend/app/workers/bulk_tasks.py

import json
import uuid
import logging
import decimal
from celery import shared_task
from decimal import Decimal

from backend.app.db import SessionLocal
from backend.app.models.bulk_job import BulkJob
from backend.app.models.credit_reservation import CreditReservation
from backend.app.services.verification_engine import verify_email_sync
from backend.app.services.minio_client import put_bytes, get_object_bytes, MINIO_BUCKET
from backend.app.services.credits_service import (
    capture_reservation_and_charge,
    release_reservation_by_job,
    add_credits,
)
from backend.app.services.pricing_service import get_cost_for_key

logger = logging.getLogger(__name__)


@shared_task(bind=True, name="process_bulk_task")
def process_bulk_task(self, job_id: str, estimated_cost: float):
    """
    Bulk email verification worker with reservation capture.
    """
    db = SessionLocal()

    try:
        job = db.query(BulkJob).filter(BulkJob.job_id == job_id).first()
        if not job:
            logger.error("Job %s not found", job_id)
            return False

        # LOAD INPUT
        assert job.input_path.startswith("s3://")
        bucket, key = job.input_path.replace("s3://", "", 1).split("/", 1)

        from backend.app.services.minio_client import get_object_bytes
        content_bytes = get_object_bytes(key)
        rows = content_bytes.decode("utf-8", errors="ignore").splitlines()

        emails = [r.strip().lower() for r in rows if "@" in r]
        emails = list(dict.fromkeys(emails))
        total = len(emails)
        job.total = total

        processed = 0
        valid = 0
        invalid = 0
        results = []

        for email in emails:
            try:
                r = verify_email_sync(email, user_id=job.user_id)
                if r.get("status") == "valid":
                    valid += 1
                else:
                    invalid += 1
                processed += 1
                results.append({"email": email, "result": r})
            except:
                invalid += 1
                processed += 1
                results.append({"email": email, "error": "verify_failed"})

            job.processed = processed
            job.valid = valid
            job.invalid = invalid
            db.add(job)
            db.commit()

        # -------------------------
        #   CALCULATE ACTUAL COST
        # -------------------------
        per_email_cost = Decimal(str(get_cost_for_key("verify.bulk_per_email") or 0))
        actual_cost = (per_email_cost * Decimal(processed)).quantize(Decimal("0.000001"))

        # -------------------------
        #  FINALIZE RESERVATIONS
        # -------------------------
        reservations = (
            db.query(CreditReservation)
            .filter(CreditReservation.job_id == job.job_id, CreditReservation.locked == True)
            .all()
        )

        remain_to_charge = actual_cost
        refund_total = Decimal("0")

        for r in reservations:
            if remain_to_charge <= 0:
                release_reservation_by_job(job.job_id)
                break

            r_amt = Decimal(r.amount)

            if r_amt <= remain_to_charge:
                capture_reservation_and_charge(r.id, type_="bulk_charge", reference=f"bulk:{job.job_id}")
                remain_to_charge -= r_amt
            else:
                # capture partial
                diff = r_amt - remain_to_charge
                r.amount = remain_to_charge
                db.add(r)
                db.commit()

                capture_reservation_and_charge(r.id, type_="bulk_charge", reference=f"bulk:{job.job_id}")
                refund_total += diff
                remain_to_charge = Decimal("0")

        # refund unused portion of estimated
        estimated_d = Decimal(str(estimated_cost))
        if estimated_d > actual_cost:
            refund_extra = (estimated_d - actual_cost).quantize(Decimal("0.000001"))
            refund_total += refund_extra
            add_credits(job.user_id, refund_extra, reference=f"{job_id}:bulk_refund")

        # -------------------------
        # STORE RESULTS IN MINIO
        # -------------------------
        output_key = f"results/{job_id}.json"
        put_bytes(output_key, json.dumps(results).encode("utf-8"))
        job.output_path = f"s3://{bucket}/{output_key}"
        job.status = "completed"

        db.add(job)
        db.commit()

        return True

    except Exception as e:
        logger.exception("bulk job %s failed: %s", job_id, e)
        job.status = "failed"
        job.error_message = str(e)
        db.add(job)
        db.commit()

        release_reservation_by_job(job.job_id)
        return False

    finally:
        db.close()
