# backend/app/workers/extractor_tasks_async.py
import io
import csv
import json
import os
import zipfile
import logging
import asyncio
from decimal import Decimal, ROUND_HALF_UP
from typing import List
import aiohttp
from backend.app.celery_app import celery_app
from backend.app.db import SessionLocal
from backend.app.models.extractor_job import ExtractorJob
from backend.app.services.extractor_engine import parse_with_bs, http_fetch  # we will use http_fetch for raw html
from backend.app.services.minio_client import get_object_bytes, put_bytes, ensure_bucket, MINIO_BUCKET
from backend.app.services.pricing_service import get_cost_for_key
from backend.app.services.credits_service import capture_reservation_by_job, release_reservation_by_job
from backend.app.services.credits_service import get_cost_for_job_estimate_key
from backend.app.services.verification_engine import verify_email_sync  # optional
from backend.app.services.extraction_utils import normalize_url  # optional helper if you have it

logger = logging.getLogger(__name__)
OUTPUT_PREFIX = "extractor/outputs"
MAX_CONCURRENCY = int(os.getenv("EXTRACTOR_MAX_CONCURRENCY", "12"))
HTTP_TIMEOUT = int(os.getenv("EXTRACTOR_HTTP_TIMEOUT", "20"))

def _dec(x) -> Decimal:
    return Decimal(str(x)).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)

async def _fetch_html(session: aiohttp.ClientSession, url: str):
    try:
        headers = {"User-Agent": "Mozilla/5.0 (compatible; EmailExtractor/1.0; +https://your-domain.com)"}
        async with session.get(url, headers=headers, timeout=HTTP_TIMEOUT) as resp:
            text = await resp.text()
            return {"status": resp.status, "text": text, "final_url": str(resp.url)}
    except Exception as e:
        return {"status": None, "text": "", "final_url": url, "error": str(e)}

def parse_urls_from_bytes(content: bytes, filename: str) -> List[str]:
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

async def _process_one(session: aiohttp.ClientSession, url: str, use_browser: bool = False):
    # For async worker we use http fetch + bs parser (safe, fast)
    try:
        http = await _fetch_html(session, url)
        text = http.get("text", "") or ""
        parsed = parse_with_bs(text, base_url=http.get("final_url"))
        return {"url": url, "status": http.get("status"), "final_url": http.get("final_url"), "emails": parsed.get("emails", []), "links": parsed.get("links", []), "error": http.get("error")}
    except Exception as e:
        logger.exception("process_one failed %s", e)
        return {"url": url, "error": str(e)}

@celery_app.task(bind=True, max_retries=2, name="extractor.process_extractor_job_async")
def process_extractor_job_async(self, job_id: str, use_browser: bool = False):
    loop = asyncio.get_event_loop()
    return loop.run_until_complete(_process_extractor_job_async(job_id, use_browser))

async def _process_extractor_job_async(job_id: str, use_browser: bool = False):
    db = SessionLocal()
    try:
        job = db.query(ExtractorJob).filter(ExtractorJob.job_id == job_id).first()
        if not job:
            logger.error("extractor async job not found: %s", job_id)
            return {"error": "job_not_found"}

        # Read input bytes (s3 or local)
        content = None
        if job.input_path and str(job.input_path).startswith("s3://"):
            parts = job.input_path.replace("s3://", "").split("/", 1)
            obj = parts[1] if len(parts) > 1 else ""
            content = get_object_bytes(obj)
            filename = obj.split("/")[-1]
        else:
            with open(job.input_path, "rb") as fh:
                content = fh.read()
            filename = job.input_path.split("/")[-1]

        urls = parse_urls_from_bytes(content, filename)
        urls = [u for u in urls if u and u.startswith(("http://", "https://"))]
        total = len(urls)
        if total == 0:
            job.status = "error"; job.error_message = "no_urls_found"; db.add(job); db.commit()
            return {"error": "no_urls_found"}

        # concurrency fetch
        connector = aiohttp.TCPConnector(limit=MAX_CONCURRENCY, ssl=False)
        timeout = aiohttp.ClientTimeout(total=HTTP_TIMEOUT + 5)
        results = []
        processed = 0
        success = 0
        fail = 0

        async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
            sem = asyncio.Semaphore(MAX_CONCURRENCY)
            async def worker(u):
                async with sem:
                    return await _process_one(session, u, use_browser=use_browser)

            tasks = [asyncio.create_task(worker(u)) for u in urls]
            for fut in asyncio.as_completed(tasks):
                r = await fut
                processed += 1
                if r.get("error"):
                    fail += 1
                else:
                    if r.get("emails"):
                        success += 1
                results.append(r)

        # write outputs to minio
        ensure_bucket()
        out_json_obj = f"{OUTPUT_PREFIX}/{job.job_id}.json"
        out_csv_obj = f"{OUTPUT_PREFIX}/{job.job_id}.csv"
        json_bytes = json.dumps({
            "job_id": job.job_id, "total": total, "processed": processed,
            "success": success, "fail": fail, "results_preview": results[:200]
        }, indent=2).encode("utf-8")

        csv_buf = io.StringIO()
        writer = csv.writer(csv_buf)
        writer.writerow(["url","emails","links","status","error"])
        for r in results:
            emails = "|".join(r.get("emails") or [])
            links = "|".join(r.get("links") or [])
            status = "ok" if not r.get("error") else "error"
            err = r.get("error") or ""
            writer.writerow([r.get("url"), emails, links, status, err])

        try:
            put_bytes(out_json_obj, json_bytes, content_type="application/json")
            put_bytes(out_csv_obj, csv_buf.getvalue().encode("utf-8"), content_type="text/csv")
        except Exception:
            logger.exception("writing outputs to minio failed")

        # Update job
        job.processed = processed
        job.success = success
        job.fail = fail
        job.output_path = f"s3://{MINIO_BUCKET}/{out_json_obj}"
        job.status = "finished"
        db.add(job)
        db.commit()

        # === Billing finalization: capture reservation(s) by job_id ===
        try:
            # capture_reservation_by_job returns dict with capture summary
            cap = capture_reservation_by_job(job.job_id, processed_count=processed)
            logger.info("capture_reservation_by_job done: %s", cap)
        except Exception:
            logger.exception("capture_reservation_by_job failed for job %s", job.job_id)

        return {"job_id": job.job_id, "processed": processed, "success": success, "fail": fail}

    except Exception as exc:
        logger.exception("extractor worker unexpected: %s", exc)
        try:
            job.status = "error"; job.error_message = "worker_failed"; db.add(job); db.commit()
        except Exception:
            pass
        raise
    finally:
        db.close()
