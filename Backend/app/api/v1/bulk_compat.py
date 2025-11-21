
# backend/app/api/v1/bulk_compat.py
from fastapi import APIRouter, UploadFile, File, Depends, Request, HTTPException
from backend.app.utils.security import get_current_user
from fastapi import status
import requests
import os

router = APIRouter(prefix="/v1/bulk", tags=["Bulk-Compat"])

# This compatibility shim proxies the old endpoint to the new one.
# It expects internal URL to be same host. If your deployments are split,
# change TARGET_BASE to the internal API URL.
TARGET_BASE = os.getenv("INTERNAL_API_BASE", "http://127.0.0.1:8000")

@router.post("/upload", status_code=status.HTTP_202_ACCEPTED)
async def upload_csv(file: UploadFile = File(...), request: Request = None, current_user = Depends(get_current_user)):
    """
    Proxy old upload route to new /api/v1/bulk/submit.
    Streams file to new endpoint; forwards Authorization header.
    """
    # read file bytes (small overhead). For large files you can write to disk and stream.
    content = await file.read()
    headers = {}
    auth = request.headers.get("authorization")
    if auth:
        headers["Authorization"] = auth

    files = {"file": (file.filename, content)}
    data = {}
    # If old clients provided webhook_url as form field, forward it
    if "webhook_url" in request.query_params:
        data["webhook_url"] = request.query_params["webhook_url"]

    url = f"{TARGET_BASE}/api/v1/bulk/submit"
    try:
        resp = requests.post(url, headers=headers, files=files, data=data, timeout=30)
    except Exception as e:
        raise HTTPException(status_code=502, detail="proxy_failed")
    if resp.status_code >= 400:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    return resp.json()
