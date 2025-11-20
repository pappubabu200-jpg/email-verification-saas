import logging
from backend.app.db import SessionLocal
from backend.app.models.api_key import ApiKey

logger = logging.getLogger(__name__)

def get_user_from_api_key(api_key: str):
    """
    Returns user object and api_key row.
    Used by:
    - API key middleware
    - Usage logging
    - Rate limiting
    - Decision maker finder
    """

    if not api_key:
        return None, None

    db = SessionLocal()
    try:
        key_row = (
            db.query(ApiKey)
            .filter(ApiKey.key == api_key, ApiKey.active == True)
            .first()
        )
        if not key_row:
            return None, None

        # joined load user
        user = key_row.user

        return user, key_row

    except Exception as e:
        logger.exception("api key lookup failed: %s", e)
        return None, None
    finally:
        db.close()
