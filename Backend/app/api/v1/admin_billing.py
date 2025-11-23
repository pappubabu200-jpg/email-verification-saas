# backend/app/api/v1/admin_billing.py
from fastapi import APIRouter, Depends, Query
from backend.app.utils.security import get_current_admin
from backend.app.db import SessionLocal
from datetime import datetime, timedelta
from sqlalchemy import func

router = APIRouter(prefix="/api/v1/admin/billing", tags=["admin-billing"])

@router.get("/overview")
def billing_overview(days: int = Query(30), admin = Depends(get_current_admin)):
    db = SessionLocal()
    try:
        UsageLog = __import__("backend.app.models.usage_log", fromlist=["UsageLog"]).UsageLog
        total_requests = db.query(func.count(UsageLog.id)).filter(UsageLog.created_at >= datetime.utcnow() - timedelta(days=days)).scalar() or 0
        total_users = db.query(func.count(func.distinct(UsageLog.user_id))).scalar() or 0
        q = db.execute("SELECT COUNT(*) FROM users").scalar()
        # Stripe stats require calling Stripe API and aggregating (if desired).
        return {"time_range_days": days, "total_api_requests": int(total_requests), "total_api_users": int(total_users), "total_users": int(q)}
    finally:
        db.close()

@router.get("/top-payers")
def top_payers(limit: int = Query(20), admin = Depends(get_current_admin)):
    db = SessionLocal()
    try:
        res = db.execute("""
            SELECT u.id, u.email, COALESCE(SUM(ct.amount),0) as paid
            FROM users u LEFT JOIN credit_transactions ct ON ct.user_id = u.id
            GROUP BY u.id ORDER BY paid DESC LIMIT :limit
        """, {"limit": limit}).fetchall()
        out = [{"id": r[0], "email": r[1], "paid": float(r[2])} for r in res]
        return {"rows": out}
    finally:
        db.close()
