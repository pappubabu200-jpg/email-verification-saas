import logging
from sqlalchemy import func
from backend.app.db import SessionLocal
from backend.app.models.usage_log import UsageLog
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

def count_requests(days: int = 7):
    db = SessionLocal()
    try:
        since = datetime.utcnow() - timedelta(days=days)
        total = db.query(func.count(UsageLog.id)).filter(UsageLog.created_at >= since).scalar() or 0
        return total
    finally:
        db.close()


def top_api_keys(days: int = 7, limit: int = 10):
    db = SessionLocal()
    try:
        since = datetime.utcnow() - timedelta(days=days)
        rows = (
            db.query(UsageLog.api_key_id, func.count(UsageLog.id).label("cnt"))
            .filter(UsageLog.created_at >= since)
            .group_by(UsageLog.api_key_id)
            .order_by(func.count(UsageLog.id).desc())
            .limit(limit)
            .all()
        )
        return [{"api_key_id": r[0], "count": int(r[1])} for r in rows]
    finally:
        db.close()


def top_endpoints(days: int = 7, limit: int = 10):
    db = SessionLocal()
    try:
        since = datetime.utcnow() - timedelta(days=days)
        rows = (
            db.query(UsageLog.endpoint, func.count(UsageLog.id).label("cnt"))
            .filter(UsageLog.created_at >= since)
            .group_by(UsageLog.endpoint)
            .order_by(func.count(UsageLog.id).desc())
            .limit(limit)
            .all()
        )
        return [{"endpoint": r[0], "count": int(r[1])} for r in rows]
    finally:
        db.close()


def daily_breakdown(days: int = 30):
    db = SessionLocal()
    try:
        results = []
        for i in range(days):
            d = datetime.utcnow().date() - timedelta(days=i)
            start = datetime(d.year, d.month, d.day)
            end = start + timedelta(days=1)

            count = (
                db.query(func.count(UsageLog.id))
                .filter(UsageLog.created_at >= start, UsageLog.created_at < end)
                .scalar()
                or 0
            )
            results.append({"date": start.strftime("%Y-%m-%d"), "count": int(count)})

        return list(reversed(results))
    finally:
        db.close()


def error_rate(days: int = 7):
    db = SessionLocal()
    try:
        since = datetime.utcnow() - timedelta(days=days)

        total = (
            db.query(func.count(UsageLog.id))
            .filter(UsageLog.created_at >= since)
            .scalar()
            or 0
        )

        errors = (
            db.query(func.count(UsageLog.id))
            .filter(UsageLog.created_at >= since, UsageLog.status_code >= 400)
            .scalar()
            or 0
        )

        rate = (errors / total * 100) if total > 0 else 0.0
        return {"total": total, "errors": errors, "error_rate_percent": round(rate, 2)}
    finally:
        db.close()
