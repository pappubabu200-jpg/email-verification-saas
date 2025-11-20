import logging
from backend.app.db import SessionLocal
from backend.app.models.usage_log import UsageLog

logger = logging.getLogger(__name__)


def log_usage(user, api_key_row, request, status_code):
    """
    Create usage log row in DB.
    Safe: never crashes API even if DB fails.
    """

    try:
        db = SessionLocal()

        record = UsageLog(
            user_id=user.id,
            api_key_id=api_key_row.id if api_key_row else None,
            endpoint=str(request.url.path),
            method=request.method,
            status_code=status_code,
            ip=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent")
        )

        db.add(record)
        db.commit()

    except Exception as e:
        logger.exception("Usage logging failed: %s", e)

    finally:
        try:
            db.close()
        except:
            pass
