# backend/app/services/storage_s3.py
import os, logging
from typing import Optional
from backend.app.config import settings

logger = logging.getLogger(__name__)

USE_S3 = bool(getattr(settings, "S3_BUCKET", ""))

if USE_S3:
    import boto3
    s3 = boto3.client(
        "s3",
        aws_access_key_id=getattr(settings, "S3_ACCESS_KEY", None),
        aws_secret_access_key=getattr(settings, "S3_SECRET_KEY", None),
        region_name=getattr(settings, "S3_REGION", None)
    )
    BUCKET = settings.S3_BUCKET
else:
    s3 = None
    BUCKET = None

def upload_file_local_or_s3(local_path: str, remote_key: str) -> str:
    """
    If S3 configured, upload file and return s3://... URL.
    Otherwise return local path.
    """
    if USE_S3 and s3:
        try:
            s3.upload_file(local_path, BUCKET, remote_key)
            return f"s3://{BUCKET}/{remote_key}"
        except Exception as e:
            logger.exception("s3 upload failed: %s", e)
            # fallback to local
            return local_path
    else:
        return local_path

def download_file_s3url(url: str, local_dest: str) -> Optional[str]:
    """
    If url is s3://... attempt download to local_dest and return local path.
    If not s3, just return url (assumed local path).
    """
    if not url:
        return None
    if url.startswith("s3://"):
        if not s3:
            return None
        try:
            _, bucket_key = url.split("s3://",1)
            bucket, key = bucket_key.split("/",1)
            s3.download_file(bucket, key, local_dest)
            return local_dest
        except Exception as e:
            logger.exception("s3 download failed: %s", e)
            return None
    return url
