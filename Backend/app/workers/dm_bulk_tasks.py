
# backend/app/workers/dm_bulk_tasks.py
import io
import csv
import logging
import zipfile
import json
import os
from decimal import Decimal
from backend.app.celery_app import celery_app
from backend.app.db import SessionLocal
from backend.app.models.bulk_job import BulkJob
from backend.app.services.dm_bulk_ws_manager import dm_bulk_ws_manager
from backend.app.services.decision_maker_service import search_decision_makers  # reuse search pipeline (sync or adapt)
from backend.app.services.minio_client import put_bytes, ensure_bucket, MINIO_BUCKET

logger = logging.getLogger(__name__)

OUTPUT_PREFIX = "outputs/dm_bulk"

@celery_app.task(bind=True, name="workers.dm_bulk_tasks.process_dm_bulk", max_retries=1)
def process_dm_bulk(self, job_id: str):
    logger.info("DM Bulk worker start %s", job_id)
    db = SessionLocal()
    try:
        job = db.query(BulkJob).filter(BulkJob.job_id == job_id).first()
        if not job:
            logger.error("Job missing %s", job_id)
            return

        # read file
        try:
            with open(job.input_path, "r", encoding="utf-8") as fh:
                reader = csv.reader(fh)
                domains = [row[0].strip().lower() for row in reader if row]
        except Exception as e:
            logger.exception("Failed to read input file: %s", e)
            job.status = "error"
            job.error_message = "input_read_failed"
            db.add(job); db.commit()
            # broadcast fail
            try:
                import asyncio
                asyncio.run(dm_bulk_ws_manager.broadcast_job(job_id, {"event":"failed","error":"input_read_failed"}))
            except Exception:
                pass
            return

        total = len(domains)
        processed = 0
        outputs = []  # list of {domain, results:[{name,email,...}]}

        # iterate domains — for each call existing DM search pipeline (synchronous to reuse verify_email_sync)
        for d in domains:
            processed += 1
            try:
                # search_decision_makers expects domain arg; this function may be sync. 
                # If your service is async, adapt to run in event loop or spawn subtask.
                results = search_decision_makers(domain=d, max_results=50, use_cache=True)
                outputs.append({"domain": d, "count": len(results), "results_preview": results[:10]})
            except Exception as e:
                logger.exception("Search failed for %s: %s", d, e)
                outputs.append({"domain": d, "error": "search_failed"})

            # update job progress in DB
            try:
                job.processed = processed
                db.add(job); db.commit()
            except Exception:
                db.rollback()

            # broadcast progress
            try:
                import asyncio
                asyncio.run(dm_bulk_ws_manager.broadcast_job(job_id, {
                    "event": "progress",
                    "job_id": job_id,
                    "processed": processed,
                    "total": total,
                }))
            except Exception:
                pass

        # Save outputs to MinIO or disk
        try:
            ensure_bucket()
            json_obj = f"{OUTPUT_PREFIX}/{job_id}.json"
            out_bytes = json.dumps({"job_id": job_id, "total": total, "processed": processed, "outputs": outputs}, indent=2).encode("utf-8")
            put_bytes(json_obj, out_bytes, content_type="application/json")
            job.output_path = f"s3://{MINIO_BUCKET}/{json_obj}"
        except Exception as e:
            logger.exception("Failed to save outputs: %s", e)
            # fallback: write local file
            try:
                outp = os.path.join("outputs", f"{job_id}.json")
                os.makedirs(os.path.dirname(outp), exist_ok=True)
                with open(outp, "wb") as fh:
                    fh.write(json.dumps(outputs, indent=2).encode("utf-8"))
                job.output_path = outp
            except Exception:
                pass

        job.status = "finished"
        db.add(job); db.commit()

        # broadcast completed
        try:
            import asyncio
            asyncio.run(dm_bulk_ws_manager.broadcast_job(job_id, {"event":"completed","job_id":job_id,"processed":processed,"total":total}))
        except Exception:
            pass

        return {"job_id": job_id, "processed": processed}

    except Exception as exc:
        logger.exception("DM bulk worker unexpected: %s", exc)
        try:
            job.status = "error"
            job.error_message = "worker_failed"
            db.add(job); db.commit()
            import asyncio
            asyncio.run(dm_bulk_ws_manager.broadcast_job(job_id, {"event":"failed","error":"worker_failed"}))
        except Exception:
            pass
        raise
    finally:
        db.close()
