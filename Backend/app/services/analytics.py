# backend/app/services/analytics.py

import logging
from datetime import datetime, timedelta, timezone
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db import async_session
from backend.app.models.usage_log import UsageLog

logger = logging.getLogger(__name__)


# -------------------------------------------------------------------
# Helper: async DB session
# -------------------------------------------------------------------
async def get_db() -> AsyncSession:
    async with async_session() as session:
        yield session


# -------------------------------------------------------------------
# 1. Total requests in last X days
# -------------------------------------------------------------------
async def count_requests(days: int = 7) -> int:
    async with async_session() as db:
        since = datetime.now(timezone.utc) - timedelta(days=days)

        result = await db.execute(
            select(func.count(UsageLog.id)).where(UsageLog.created_at >= since)
        )

        return int(result.scalar() or 0)


# -------------------------------------------------------------------
# 2. Top API keys by traffic
# -------------------------------------------------------------------
async def top_api_keys(days: int = 7, limit: int = 10):
    async with async_session() as db:
        since = datetime.now(timezone.utc) - timedelta(days=days)

        result = await db.execute(
            select(UsageLog.api_key_id, func.count(UsageLog.id).label("cnt"))
            .where(UsageLog.created_at >= since)
            .group_by(UsageLog.api_key_id)
            .order_by(func.count(UsageLog.id).desc())
            .limit(limit)
        )

        rows = result.all()

        return [
            {"api_key_id": row[0], "count": int(row[1])}
            for row in rows
        ]


# -------------------------------------------------------------------
# 3. Top endpoints used
# -------------------------------------------------------------------
async def top_endpoints(days: int = 7, limit: int = 10):
    async with async_session() as db:
        since = datetime.now(timezone.utc) - timedelta(days=days)

        result = await db.execute(
            select(UsageLog.endpoint, func.count(UsageLog.id).label("cnt"))
            .where(UsageLog.created_at >= since)
            .group_by(UsageLog.endpoint)
            .order_by(func.count(UsageLog.id).desc())
            .limit(limit)
        )

        rows = result.all()

        return [{"endpoint": r[0], "count": int(r[1])} for r in rows]


# -------------------------------------------------------------------
# 4. Daily traffic breakdown
# -------------------------------------------------------------------
async def daily_breakdown(days: int = 30):
    async with async_session() as db:
        results = []

        for i in range(days):
            day = datetime.now(timezone.utc).date() - timedelta(days=i)
            start = datetime(day.year, day.month, day.day, tzinfo=timezone.utc)
            end = start + timedelta(days=1)

            count_res = await db.execute(
                select(func.count(UsageLog.id))
                .where(UsageLog.created_at >= start)
                .where(UsageLog.created_at < end)
            )

            count = int(count_res.scalar() or 0)
            results.append({"date": start.strftime("%Y-%m-%d"), "count": count})

        return list(reversed(results))


# -------------------------------------------------------------------
# 5. Error rate calculation
# -------------------------------------------------------------------
async def error_rate(days: int = 7):
    async with async_session() as db:
        since = datetime.now(timezone.utc) - timedelta(days=days)

        total_res = await db.execute(
            select(func.count(UsageLog.id)).where(UsageLog.created_at >= since)
        )
        total = int(total_res.scalar() or 0)

        error_res = await db.execute(
            select(func.count(UsageLog.id)).where(
                UsageLog.created_at >= since,
                UsageLog.status_code >= 400
            )
        )
        errors = int(error_res.scalar() or 0)

        rate = (errors / total * 100) if total > 0 else 0.0

        return {
            "total": total,
            "errors": errors,
            "error_rate_percent": round(rate, 2)
        }
