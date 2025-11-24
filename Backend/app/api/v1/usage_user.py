# backend/app/api/v1/usage_user.py
from fastapi import APIRouter, Depends, HTTPException, Query
from typing import List, Dict, Any
from backend.app.utils.security import get_current_user
from backend.app.db import SessionLocal
from datetime import datetime, timedelta
from sqlalchemy import func
import logging

router = APIRouter(prefix="/api/v1/usage", tags=["usage"])
logger = logging.getLogger(__name__)

@router.get("/me")
def my_usage(days: int = Query(7, ge=1, le=365), current_user = Depends(get_current_user)):
    """
    Return simple per-day usage summary for the authenticated user.
    """
    user = current_user
    if not user:
        raise HTTPException(status_code=401, detail="auth_required")

    try:
        UsageLog = __import__("backend.app.models.usage_log", fromlist=["UsageLog"]).UsageLog
    except Exception:
        raise HTTPException(status_code=501, detail="usage_model_missing")

    db = SessionLocal()
    try:
        since = datetime.utcnow() - timedelta(days=days)
        total_requests = db.query(func.count(UsageLog.id)).filter(UsageLog.user_id == user.id, UsageLog.created_at >= since).scalar() or 0
        per_endpoint = db.query(UsageLog.endpoint, func.count(UsageLog.id).label("cnt")).filter(UsageLog.user_id == user.id, UsageLog.created_at >= since).group_by(UsageLog.endpoint).order_by(func.count(UsageLog.id).desc()).limit(20).all()
        top = [{"endpoint": r[0], "count": int(r[1])} for r in per_endpoint]
        return {"user_id": user.id, "days": days, "total_requests": int(total_requests), "top_endpoints": top}
    finally:
        db.close()
