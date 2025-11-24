# backend/app/services/minio_client.py
from minio import Minio
from minio.error import S3Error
from backend.app.config import settings
import io, logging

logger = logging.getLogger(__name__)

MINIO_ENDPOINT = getattr(settings, "MINIO_ENDPOINT", "localhost:9000")
MINIO_ACCESS_KEY = getattr(settings, "MINIO_ACCESS_KEY", "minioadmin")
MINIO_SECRET_KEY = getattr(settings, "MINIO_SECRET_KEY", "minioadmin")
MINIO_SECURE = getattr(settings, "MINIO_SECURE", False)
MINIO_BUCKET = getattr(settings, "MINIO_BUCKET", "email-saas-objects")

_client = None

def client() -> Minio:
    global _client
    if _client is None:
        _client = Minio(
            MINIO_ENDPOINT,
            access_key=MINIO_ACCESS_KEY,
            secret_key=MINIO_SECRET_KEY,
            secure=bool(MINIO_SECURE),
        )
    return _client

def ensure_bucket(bucket_name: str = None):
    """
    Create bucket if missing. Safe to call at startup.
    """
    bucket_name = bucket_name or MINIO_BUCKET
    try:
        c = client()
        if not c.bucket_exists(bucket_name):
            c.make_bucket(bucket_name)
            logger.info("Created minio bucket: %s", bucket_name)
    except S3Error as e:
        logger.exception("Minio error while ensuring bucket %s: %s", bucket_name, e)
        raise

def put_bytes(object_name: str, data: bytes, content_type: str = "application/octet-stream"):
    c = client()
    ensure_bucket()
    try:
        c.put_object(
            MINIO_BUCKET,
            object_name,
            io.BytesIO(data),
            length=len(data),
            content_type=content_type,
        )
        return f"s3://{MINIO_BUCKET}/{object_name}"
    except Exception as e:
        logger.exception("minio put failed: %s", e)
        raise

def get_object_bytes(object_name: str) -> bytes:
    c = client()
    try:
        r = c.get_object(MINIO_BUCKET, object_name)
        data = r.read()
        r.close()
        r.release_conn()
        return data
    except Exception as e:
        logger.exception("minio get failed: %s", e)
        raise
# backend/app/services/minio_client.py
from minio import Minio
from minio.error import S3Error
from backend.app.config import settings
import io, logging

logger = logging.getLogger(__name__)

MINIO_ENDPOINT = getattr(settings, "MINIO_ENDPOINT", "localhost:9000")
MINIO_ACCESS_KEY = getattr(settings, "MINIO_ACCESS_KEY", "minioadmin")
MINIO_SECRET_KEY = getattr(settings, "MINIO_SECRET_KEY", "minioadmin")
MINIO_SECURE = getattr(settings, "MINIO_SECURE", False)
MINIO_BUCKET = getattr(settings, "MINIO_BUCKET", "email-saas-objects")

_client = None

def client():
    global _client
    if _client is None:
        _client = Minio(
            MINIO_ENDPOINT,
            access_key=MINIO_ACCESS_KEY,
            secret_key=MINIO_SECRET_KEY,
            secure=bool(MINIO_SECURE),
        )
    return _client

def ensure_bucket(bucket_name: str = None):
    bucket_name = bucket_name or MINIO_BUCKET
    c = client()
    try:
        if not c.bucket_exists(bucket_name):
            c.make_bucket(bucket_name)
            logger.info("Created minio bucket: %s", bucket_name)
    except S3Error as e:
        logger.exception("Minio S3Error: %s", e)
        raise
    except Exception as e:
        logger.exception("Ensure minio bucket failed: %s", e)
        raise

def put_bytes(object_name: str, data: bytes, content_type: str = "application/octet-stream"):
    c = client()
    ensure_bucket()
    try:
        c.put_object(
            MINIO_BUCKET,
            object_name,
            io.BytesIO(data),
            length=len(data),
            content_type=content_type,
        )
        return f"s3://{MINIO_BUCKET}/{object_name}"
    except Exception as e:
        logger.exception("minio put failed: %s", e)
        raise

def get_object_bytes(object_name: str) -> bytes:
    c = client()
    try:
        res = c.get_object(MINIO_BUCKET, object_name)
        data = res.read()
        res.close()
        res.release_conn()
        return data
    except Exception as e:
        logger.exception("minio get failed: %s", e)
        raise 

# backend/app/services/minio_client.py
"""
MinIO client wrapper with fallback to local filesystem.
Requires environment variables:
  MINIO_ENDPOINT, MINIO_ACCESS_KEY, MINIO_SECRET_KEY, MINIO_BUCKET
If MINIO_ENABLED is "false" (case-insensitive), we fallback to local storage
under settings.MINIO_LOCAL_PATH (default: /tmp/minio_fallback).
"""

from typing import Optional
import os
import io
import logging

logger = logging.getLogger(__name__)

try:
    from minio import Minio
    from minio.error import S3Error
    MINIO_AVAILABLE = True
except Exception:
    MINIO_AVAILABLE = False

from backend.app.config import settings

MINIO_BUCKET = getattr(settings, "MINIO_BUCKET", "email-saas")
MINIO_ENABLED = str(getattr(settings, "MINIO_ENABLED", "true")).lower() != "false"
MINIO_LOCAL_PATH = getattr(settings, "MINIO_LOCAL_PATH", "/tmp/minio_fallback")

_client: Optional[Minio] = None

def client() -> Optional[Minio]:
    global _client
    if _client:
        return _client
    if not MINIO_AVAILABLE or not MINIO_ENABLED:
        return None
    endpoint = getattr(settings, "MINIO_ENDPOINT", None)
    access = getattr(settings, "MINIO_ACCESS_KEY", None)
    secret = getattr(settings, "MINIO_SECRET_KEY", None)
    use_secure = getattr(settings, "MINIO_SECURE", "false").lower() == "true"
    if not endpoint or not access or not secret:
        logger.warning("MinIO credentials not set; falling back to local storage")
        return None
    _client = Minio(endpoint, access_key=access, secret_key=secret, secure=use_secure)
    return _client

def ensure_bucket() -> None:
    c = client()
    if c:
        exists = c.bucket_exists(MINIO_BUCKET)
        if not exists:
            c.make_bucket(MINIO_BUCKET)
    else:
        os.makedirs(MINIO_LOCAL_PATH, exist_ok=True)

def put_bytes(object_name: str, data: bytes, content_type: str = "application/octet-stream") -> str:
    """
    Upload bytes and return object path (s3://bucket/object or local path)
    """
    c = client()
    if c:
        # minio client's put_object expects a stream
        c.put_object(MINIO_BUCKET, object_name, io.BytesIO(data), length=len(data), content_type=content_type)
        return f"s3://{MINIO_BUCKET}/{object_name}"
    # fallback: write to local disk
    dest = os.path.join(MINIO_LOCAL_PATH, object_name.replace("/", os.sep))
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    with open(dest, "wb") as fh:
        fh.write(data)
    return dest

def get_object_bytes(object_name: str) -> bytes:
    """
    Read object bytes from minio or fallback local path
    """
    c = client()
    if c:
        try:
            obj = c.get_object(MINIO_BUCKET, object_name)
            data = obj.read()
            obj.close()
            obj.release_conn()
            return data
        except Exception as e:
            logger.exception("minio get_object failed: %s", e)
            raise
    # fallback
    path = os.path.join(MINIO_LOCAL_PATH, object_name.replace("/", os.sep))
    with open(path, "rb") as fh:
        return fh.read()

# backend/app/services/minio_client.py
"""
MinIO helper wrapper using 'minio' package.

Install dependency:
    pip install minio

Provides:
 - client: Minio client instance
 - MINIO_BUCKET: default bucket name from settings
 - ensure_bucket() -> creates bucket if missing
 - put_bytes(path, bytes, content_type=None) -> returns object path
 - get_object_bytes(path) -> returns bytes
 - presign_get(bucket, object_name, expires=3600) -> returns presigned URL
"""

from minio import Minio
from minio.error import S3Error
from backend.app.config import settings
import io, logging

logger = logging.getLogger(__name__)

MINIO_ENDPOINT = getattr(settings, "MINIO_ENDPOINT", "minio:9000")
MINIO_ACCESS_KEY = getattr(settings, "MINIO_ROOT_USER", getattr(settings, "MINIO_ACCESS_KEY", "minioadmin"))
MINIO_SECRET_KEY = getattr(settings, "MINIO_ROOT_PASSWORD", getattr(settings, "MINIO_SECRET_KEY", "minioadmin"))
MINIO_BUCKET = getattr(settings, "MINIO_BUCKET", "app-uploads")

# Create MinIO client
client = Minio(
    MINIO_ENDPOINT,
    access_key=MINIO_ACCESS_KEY,
    secret_key=MINIO_SECRET_KEY,
    secure=str(getattr(settings, "MINIO_SECURE", "false")).lower() in ("1", "true", "yes")
)

def ensure_bucket(bucket_name: str = None):
    b = bucket_name or MINIO_BUCKET
    try:
        found = client.bucket_exists(b)
        if not found:
            client.make_bucket(b)
    except Exception as e:
        logger.exception("ensure_bucket failed: %s", e)
        raise

def put_bytes(object_name: str, data: bytes, content_type: str = "application/octet-stream", bucket: str = None):
    """
    Upload bytes to MinIO. object_name is path like 'inputs/abc.csv'
    Returns s3://bucket/object_name
    """
    b = bucket or MINIO_BUCKET
    ensure_bucket(b)
    try:
        client.put_object(b, object_name, io.BytesIO(data), length=len(data), content_type=content_type)
        return f"s3://{b}/{object_name}"
    except Exception:
        logger.exception("put_bytes failed")
        raise

def get_object_bytes(object_name: str, bucket: str = None) -> bytes:
    b = bucket or MINIO_BUCKET
    try:
        resp = client.get_object(b, object_name)
        data = resp.read()
        resp.close()
        resp.release_conn()
        return data
    except Exception:
        logger.exception("get_object_bytes failed")
        raise

def presign_get(bucket: str, object_name: str, expires: int = 3600) -> str:
    """
    Return presigned GET URL for object. expires in seconds (int).
    """
    try:
        return client.presigned_get_object(bucket, object_name, expires=expires)
    except Exception:
        logger.exception("presign_get failed")
        raise


