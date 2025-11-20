from sqlalchemy.orm import Session
from backend.app.models.api_key import ApiKey


def reset_daily_usage(db: Session):
    """
    Reset usage for all API keys — run daily with Celery beat.
    """
    db.query(ApiKey).update({ApiKey.used_today: 0})
    db.commit()
