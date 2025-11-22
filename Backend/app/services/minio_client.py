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
