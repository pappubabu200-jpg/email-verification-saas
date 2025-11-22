
from fastapi import APIRouter, Depends, Query
from backend.app.utils.security import get_current_admin
from backend.app.db import SessionLocal
from datetime import datetime, timedelta
from sqlalchemy import func

router = APIRouter(prefix="/api/v1/admin/analytics", tags=["admin-analytics"])

@router.get("/usage-summary")
def usage_summary(days: int = Query(7), admin = Depends(get_current_admin)):
    """
    Returns summary: total requests, total unique users, total api keys, top endpoints
    """
    db = SessionLocal()
    try:
        since = datetime.utcnow() - timedelta(days=days)
        UsageLog = __import__("backend.app.models.usage_log", fromlist=["UsageLog"]).UsageLog
        q_total = db.query(func.count(UsageLog.id)).filter(UsageLog.created_at >= since).scalar() or 0
        q_users = db.query(func.count(func.distinct(UsageLog.user_id))).filter(UsageLog.created_at >= since).scalar() or 0
        q_keys = db.query(func.count(func.distinct(UsageLog.api_key_id))).filter(UsageLog.created_at >= since).scalar() or 0
        top_endpoints = db.query(UsageLog.endpoint, func.count(UsageLog.id).label("cnt")).filter(UsageLog.created_at >= since).group_by(UsageLog.endpoint).order_by(func.count(UsageLog.id).desc()).limit(10).all()
        top = [{"endpoint": r[0], "count": int(r[1])} for r in top_endpoints]
        return {"days": days, "total_requests": int(q_total), "unique_users": int(q_users), "unique_api_keys": int(q_keys), "top_endpoints": top}
    finally:
        db.close()

@router.get("/daily-trends")
def daily_trends(days: int = Query(30), admin = Depends(get_current_admin)):
    db = SessionLocal()
    try:
        UsageLog = __import__("backend.app.models.usage_log", fromlist=["UsageLog"]).UsageLog
        data = []
        for i in range(days):
            dt = datetime.utcnow().date() - timedelta(days=i)
            start = datetime(dt.year, dt.month, dt.day)
            end = start + timedelta(days=1)
            cnt = db.query(func.count(UsageLog.id)).filter(UsageLog.created_at >= start, UsageLog.created_at < end).scalar() or 0
            data.append({"date": start.strftime("%Y-%m-%d"), "count": int(cnt)})
        data.reverse()
        return {"days": days, "series": data}
    finally:
        db.close()
        # backend/app/api/v1/admin_analytics.py
from fastapi import APIRouter, Depends, Query
from backend.app.utils.security import get_current_admin
from backend.app.db import SessionLocal
from datetime import datetime, timedelta
from sqlalchemy import func

router = APIRouter(prefix="/api/v1/admin/analytics", tags=["admin-analytics"])

@router.get("/usage-summary")
def usage_summary(days: int = Query(7), admin = Depends(get_current_admin)):
    db = SessionLocal()
    try:
        since = datetime.utcnow() - timedelta(days=days)
        UsageLog = __import__("backend.app.models.usage_log", fromlist=["UsageLog"]).UsageLog
        total = db.query(func.count(UsageLog.id)).filter(UsageLog.created_at >= since).scalar() or 0
        users = db.query(func.count(func.distinct(UsageLog.user_id))).filter(UsageLog.created_at >= since).scalar() or 0
        keys = db.query(func.count(func.distinct(UsageLog.api_key))).filter(UsageLog.created_at >= since).scalar() or 0
        top = db.query(UsageLog.endpoint, func.count(UsageLog.id).label("cnt")).filter(UsageLog.created_at >= since).group_by(UsageLog.endpoint).order_by(func.count(UsageLog.id).desc()).limit(10).all()
        top_list = [{"endpoint": r[0], "count": int(r[1])} for r in top]
        return {"days": days, "total_requests": int(total), "unique_users": int(users), "unique_api_keys": int(keys), "top_endpoints": top_list}
    finally:
        db.close()

@router.get("/daily-trends")
def daily_trends(days: int = Query(30), admin = Depends(get_current_admin)):
    db = SessionLocal()
    try:
        UsageLog = __import__("backend.app.models.usage_log", fromlist=["UsageLog"]).UsageLog
        series = []
        for i in range(days):
            d = (datetime.utcnow().date() - timedelta(days=(days - i - 1)))
            start = datetime(d.year, d.month, d.day)
            end = start + timedelta(days=1)
            cnt = db.query(func.count(UsageLog.id)).filter(UsageLog.created_at >= start, UsageLog.created_at < end).scalar() or 0
            series.append({"date": start.strftime("%Y-%m-%d"), "count": int(cnt)})
        return {"days": days, "series": series}
    finally:
        db.close()


