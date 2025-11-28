
# backend/app/routers/dm_bulk.py
from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException, status
from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession
import uuid
import io
import csv
import json
import os
from typing import List, Optional

from backend.app.db import get_async_db  # adapt to your project get_async_db
from backend.app.models.bulk_job import BulkJob  # reuse your BulkJob model or create DM-specific
from backend.app.celery_app import celery_app as celery

from backend.app.services.dm_bulk_ws_manager import dm_bulk_ws_manager  # ws manager

router = APIRouter(prefix="/dm/bulk", tags=["dm_bulk"])

# NOTE: assumes BulkJob model exists with fields: job_id (str), user_id (int/null), status, total, processed, input_path, output_path, created_at, updated_at
# adapt model fields as needed

@router.post("/create")
async def create_dm_bulk_job(
    request: Request,
    file: Optional[UploadFile] = File(None),
    domains_text: Optional[str] = Form(None),
    user_id: Optional[int] = Form(None),
    db: AsyncSession = Depends(get_async_db),
):
    """
    Create a DM bulk job. Accepts either a CSV upload (one domain per row) or a textarea domains_text (newline separated).
    Returns: { job_id }
    """
    if (file is None) and (not domains_text):
        raise HTTPException(status_code=400, detail="Provide CSV upload or domains_text")

    # parse domains
    domains: List[str] = []
    if file:
        contents = await file.read()
        try:
            text = contents.decode("utf-8", errors="ignore")
        except Exception:
            text = str(contents)
        reader = csv.reader(io.StringIO(text))
        for row in reader:
            for col in row:
                col = str(col).strip()
                if col:
                    domains.append(col.lower())
    else:
        for line in (domains_text or "").splitlines():
            v = line.strip()
            if v:
                domains.append(v.lower())

    domains = list(dict.fromkeys(domains))  # dedupe
    if len(domains) == 0:
        raise HTTPException(status_code=400, detail="No domains found")

    # write upload to disk (or minio in prod). Use uploads/dm_bulk_{uuid}.csv
    job_id = str(uuid.uuid4())
    uploads_folder = os.getenv("DM_UPLOADS_FOLDER", "uploads/dm_bulk")
    os.makedirs(uploads_folder, exist_ok=True)
    file_path = os.path.join(uploads_folder, f"{job_id}.csv")

    with open(file_path, "w", encoding="utf-8") as fh:
        w = csv.writer(fh)
        for d in domains:
            w.writerow([d])

    # create DB job record (adapt to your ORM/repo)
    job = BulkJob(
        job_id=job_id,
        user_id=user_id,
        status="queued",
        total=len(domains),
        processed=0,
        input_path=file_path,
        output_path=None,
    )
    db.add(job)
    await db.commit()

    # Enqueue worker (Celery) — worker function = workers.dm_bulk_tasks.process_dm_bulk
    celery.send_task("workers.dm_bulk_tasks.process_dm_bulk", args=[job_id], kwargs={})

    # optional immediate WS broadcast: queued
    try:
        await dm_bulk_ws_manager.broadcast_job(job_id, {"event": "queued", "job_id": job_id, "total": len(domains)})
    except Exception:
        pass

    return {"job_id": job_id}


@router.get("/{job_id}")
async def get_dm_bulk_job(job_id: str, db: AsyncSession = Depends(get_async_db)):
    job = await db.get(BulkJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return {
        "job_id": job.job_id,
        "status": job.status,
        "total": job.total,
        "processed": job.processed,
        "output_path": job.output_path,
        "results_preview": getattr(job, "results_preview", None),
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "updated_at": job.updated_at.isoformat() if job.updated_at else None,
    }
