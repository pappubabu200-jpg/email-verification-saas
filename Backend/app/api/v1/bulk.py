from fastapi import APIRouter, UploadFile, File, Depends, HTTPException
import io, uuid
from backend.app.services.csv_parser import extract_emails_from_csv_bytes
from backend.app.services.bulk_processor import submit_bulk_job
from backend.app.utils.security import get_current_user

router = APIRouter(prefix="/v1/bulk", tags=["Bulk"])

@router.post("/upload")
async def upload_csv(file: UploadFile = File(...), current_user = Depends(get_current_user)):
    content = await file.read()
    emails = extract_emails_from_csv_bytes(content)
    if not emails:
        raise HTTPException(status_code=400, detail="no_emails_found")
    job_id = f"job-{uuid.uuid4().hex[:12]}"
    res = submit_bulk_job(getattr(current_user, "id", None), job_id, emails)
    return {"job_id": job_id, "queued": res.get("queued", 0)}
