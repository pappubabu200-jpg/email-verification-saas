import logging

logger = logging.getLogger(__name__)

def job_watcher():
    """
    Placeholder for future job status tracking.
    Could aggregate celery results, update job completion,
    send admin notifications, etc.
    """
    logger.debug("job watcher tick")
"""
Job Watcher:
Runs every X seconds via Celery Beat.
Handles:

✔ Bulk job progress tracking
✔ Reservation capture when job completes
✔ Release unused credits for failed/partial jobs
✔ Updates job state inside Redis
✔ Deletes job keys after completion
"""

import json
import logging
from datetime import datetime

from backend.app.db import SessionLocal
from backend.app.services.credits_service import capture_reservation, release_reservation

logger = logging.getLogger(__name__)

try:
    import redis
    REDIS = redis.from_url("redis://redis:6379/0")
except:
    REDIS = None


# Redis Key Format
# job:{job_id}:meta → {"total": N, "reservation_id": R, "user_id": U}
# job:{job_id}:done → integer count
# job:{job_id}:error → integer count


def get_job_meta(job_id: str):
    if not REDIS:
        return None
    d = REDIS.get(f"job:{job_id}:meta")
    if not d:
        return None
    return json.loads(d)


def get_done_count(job_id: str):
    if not REDIS:
        return 0
    val = REDIS.get(f"job:{job_id}:done")
    return int(val) if val else 0


def get_error_count(job_id: str):
    if not REDIS:
        return 0
    val = REDIS.get(f"job:{job_id}:error")
    return int(val) if val else 0


def delete_job_keys(job_id: str):
    if REDIS:
        REDIS.delete(f"job:{job_id}:meta")
        REDIS.delete(f"job:{job_id}:done")
        REDIS.delete(f"job:{job_id}:error")


def process_job(job_id: str, meta: dict):
    """
    Decide if a bulk job is finished and capture / release credits.
    """
    total = meta["total"]
    reservation_id = meta["reservation_id"]
    user_id = meta["user_id"]

    done = get_done_count(job_id)
    error = get_error_count(job_id)

    logger.info(f"[JobWatcher] Job {job_id}: total={total} done={done} error={error}")

    if done + error < total:
        # Still in progress
        return False

    # Job finished. Perform credit settlement.
    db = SessionLocal()
    try:
        used = done  # number of successful checks
        failed = error
        total_reserved = total

        if failed == 0:
            # Everything succeeded → capture full reservation
            capture_reservation(db, reservation_id, type_="bulk_capture")
            logger.info(f"[JobWatcher] Job {job_id}: captured full reservation")
        else:
            # Partial failure
            used_amount = used
            failed_amount = failed

            # Capture used credits only
            if used_amount > 0:
                # Create a proportional capture for `used_amount`
                # release the full reservation, then charge only used
                release_reservation(db, reservation_id)

                from backend.app.services.credits_service import add_credits, get_balance
                from backend.app.models.credit_transaction import CreditTransaction

                # Charge only used amount
                bal = get_balance(db, user_id)
                new_balance = bal - used_amount

                tx = CreditTransaction(
                    user_id=user_id,
                    amount=-used_amount,
                    balance_after=new_balance,
                    type="partial_bulk_capture",
                    reference=job_id,
                )
                db.add(tx)
                db.commit()

                logger.info(f"[JobWatcher] Job {job_id}: partially captured {used_amount} credits")

            else:
                # No successful emails → release reservation
                release_reservation(db, reservation_id)
                logger.info(f"[JobWatcher] Job {job_id}: released full reservation")

    except Exception as e:
        logger.exception(f"[JobWatcher] Error processing job {job_id}: {e}")
    finally:
        db.close()

    delete_job_keys(job_id)
    return True


def scan_jobs():
    """
    Scan all job meta keys and process if finished.
    Called by Celery Beat under scheduler.py.
    """
    if not REDIS:
        logger.error("Redis not available, cannot scan jobs")
        return

    keys = REDIS.keys("job:*:meta")
    for k in keys:
        try:
            job_id = k.decode().split(":")[1]
            meta = get_job_meta(job_id)
            if not meta:
                continue
            process_job(job_id, meta)
        except Exception as e:
            logger.exception(f"[JobWatcher] Failed to scan key {k}: {e}")
