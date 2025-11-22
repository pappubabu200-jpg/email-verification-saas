import datetime
from backend.app.services.minio_client import client, MINIO_BUCKET

def generate_signed_url(object_name: str, expiry_seconds: int = 1800) -> str:
    """
    Generates a temporary signed URL to download an object from MinIO.
    """
    return client.presigned_get_object(
        MINIO_BUCKET,
        object_name,
        expires=expiry_seconds
    )
