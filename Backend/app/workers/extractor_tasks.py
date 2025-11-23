from backend.app.celery_app import celery_app

@celery_app.task(name="backend.app.workers.extractor_tasks.extract_from_url")
def extract_from_url(url: str, job_id: str, user_id: int):
    """
    TODO:
    Implement actual scraper (requests + bs4 + regex + JS fetch)
    """
    return {
        "job_id": job_id,
        "url": url,
        "emails": [],
        "status": "pending (not implemented)"
    }
# backend/app/workers/extractor_tasks.py
import logging
from celery import shared_task
from backend.app.db import SessionLocal
from backend.app.models.extractor_job import ExtractorJob
from backend.app.services.extractor_engine import extract_url
from backend.app.services.credits_service import capture_reservation_and_charge, release_reservation_by_job
from backend.app.services.pricing_service import get_cost_for_key
from decimal import Decimal

logger = logging.getLogger(__name__)

@shared_task(bind=True, name="process_extractor_job")
def process_extractor_job(self, job_id: str, estimated_cost: float):
    db = SessionLocal()
    try:
        job = db.query(ExtractorJob).filter(ExtractorJob.job_id == job_id).first()
        if not job:
            return {"error": "job_not_found"}

        results = []
        success = 0
        for url in job.urls:
            try:
                res = extract_url(url)
                results.append({"url": url, "result": res})
                if res.get("emails"):
                    success += 1
            except Exception:
                results.append({"url": url, "error": "extract_failed"})

        job.status = "finished"
        job.result_preview = str(results[:50])
        db.add(job); db.commit()

        # compute actual cost and finalize reservations similar to bulk
        per_cost = Decimal(str(get_cost_for_key("extractor.bulk_per_url") or 0))
        actual_cost = (per_cost * Decimal(len(job.urls))).quantize(Decimal("0.000001"))

        # find reservations and capture/release as in bulk worker
        # ... (reuse capture_reservation_and_charge & release_reservation_by_job)
        return {"ok": True, "processed": len(job.urls), "success": success}
    finally:
        db.close()



# backend/app/workers/extractor_tasks.py
import io
import csv
import json
import os
import zipfile
import logging
from decimal import Decimal, ROUND_HALF_UP
from backend.app.celery_app import celery_app
from backend.app.db import SessionLocal
from backend.app.models.extractor_job import ExtractorJob
from backend.app.services.extractor_engine import extract_url
from backend.app.services.minio_client import get_object_bytes, put_bytes, ensure_bucket, MINIO_BUCKET
from backend.app.services.pricing_service import get_cost_for_key

logger = logging.getLogger(__name__)

OUTPUT_PREFIX = "extractor/outputs"

def _dec(x) -> Decimal:
    return Decimal(str(x)).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)

def parse_urls_from_bytes(content: bytes, filename: str):
    urls = []
    try:
        if filename.lower().endswith(".zip"):
            z = zipfile.ZipFile(io.BytesIO(content))
            for name in z.namelist():
                if name.endswith("/") or name.startswith("__MACOSX"):
                    continue
                if name.lower().endswith((".txt", ".csv")):
                    raw = z.read(name).decode("utf-8", errors="ignore")
                    for line in raw.splitlines():
                        s = line.strip()
                        if s:
                            urls.append(s)
        elif filename.lower().endswith(".csv"):
            raw = content.decode("utf-8", errors="ignore")
            import csv, io
            for row in csv.reader(io.StringIO(raw)):
                if not row:
                    continue
                for col in row:
                    v = col.strip()
                    if v:
                        urls.append(v)
                        break
        else:
            raw = content.decode("utf-8", errors="ignore")
            for line in raw.splitlines():
                s = line.strip()
                if s:
                    urls.append(s)
    except Exception as e:
        logger.exception("parse_urls failed: %s", e)
    return list(dict.fromkeys(urls))

@celery_app.task(bind=True, max_retries=2)
def process_extractor_job(self, job_id: str, use_browser: bool = False):
    db = SessionLocal()
    try:
        job = db.query(ExtractorJob).filter(ExtractorJob.job_id == job_id).first()
        if not job:
            logger.error("extractor job not found: %s", job_id)
            return {"error": "job_not_found"}

        # read input bytes
        content = None
        if job.input_path and str(job.input_path).startswith("s3://"):
            parts = job.input_path.replace("s3://", "").split("/", 1)
            obj = parts[1] if len(parts) > 1 else ""
            content = get_object_bytes(obj)
            filename = obj.split("/")[-1]
        else:
            # local path
            try:
                with open(job.input_path, "rb") as fh:
                    content = fh.read()
                filename = job.input_path.split("/")[-1]
            except Exception as e:
                logger.exception("read input failed: %s", e)
                job.status = "error"; job.error_message = "input_read_failed"
                db.add(job); db.commit()
                return {"error": "input_read_failed"}

        # parse urls
        urls = parse_urls_from_bytes(content, filename)
        urls = [u for u in urls if u and u.startswith(("http://","https://"))]
        total = len(urls)
        if total == 0:
            job.status = "error"; job.error_message = "no_urls_found"
            db.add(job); db.commit()
            return {"error": "no_urls_found"}

        results = []
        processed = 0
        success = 0
        fail = 0

        for url in urls:
            processed += 1
            try:
                item = extract_url(url, parse_links=True, use_browser=use_browser)
                results.append({"url": url, "result": item})
                if item.get("emails"):
                    success += 1
                else:
                    # consider as not found (still success for extraction)
                    pass
            except Exception as e:
                logger.exception("extract fail %s: %s", url, e)
                results.append({"url": url, "error": str(e)})
                fail += 1

        # write outputs to MinIO
        ensure_bucket()
        out_json_obj = f"{OUTPUT_PREFIX}/{job.job_id}.json"
        out_csv_obj = f"{OUTPUT_PREFIX}/{job.job_id}.csv"

        json_bytes = json.dumps({
            "job_id": job.job_id,
            "total": total,
            "processed": processed,
            "success": success,
            "fail": fail,
            "results_preview": results[:200]
        }, indent=2).encode("utf-8")

        csv_buf = io.StringIO()
        writer = csv.writer(csv_buf)
        writer.writerow(["url","emails","links","status","error"])
        for r in results:
            res = r.get("result") or {}
            emails = "|".join(res.get("emails") or [])
            links = "|".join(res.get("links") or [])
            status = "ok" if "result" in r else "error"
            err = r.get("error") or ""
            writer.writerow([r.get("url"), emails, links, status, err])

        try:
            json_path = put_bytes(out_json_obj, json_bytes, content_type="application/json")
            csv_path = put_bytes(out_csv_obj, csv_buf.getvalue().encode("utf-8"), content_type="text/csv")
        except Exception as e:
            logger.exception("writing outputs failed: %s", e)
            # still proceed to update job row

        # update job
        job.processed = processed
        job.success = success
        job.fail = fail
        job.output_path = f"s3://{MINIO_BUCKET}/{out_json_obj}"
        job.status = "finished"
        db.add(job)
        db.commit()

        # NOTE: billing capture/refund: we expect reservation.job_id to be set earlier.
        # Worker can locate reservations and call capture if you implemented capture_reservation_by_job.
        # That flow is project-specific; implement in credits_service and call here if desired.

        return {"job_id": job.job_id, "processed": processed, "success": success, "fail": fail}

    except Exception as exc:
        logger.exception("extractor worker unexpected: %s", exc)
        try:
            job.status = "error"; job.error_message = "worker_failed"
            db.add(job); db.commit()
        except Exception:
            pass
        raise
    finally:
        db.close()
