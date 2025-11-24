# backend/app/api/v1/plans.py
from fastapi import APIRouter, Depends, HTTPException
from typing import List, Dict, Any
from backend.app.utils.security import get_current_admin
from backend.app.db import SessionLocal
import logging

router = APIRouter(prefix="/api/v1/plans", tags=["plans"])
logger = logging.getLogger(__name__)

# dynamic import so repo doesn't break if plan model/service not present
try:
    from backend.app.services.plan_service import get_all_plans, get_plan_by_name, seed_default_plans
    PLAN_SERVICE_AVAILABLE = True
except Exception:
    PLAN_SERVICE_AVAILABLE = False

@router.get("/", response_model=List[Dict[str, Any]])
def list_plans():
    """
    List plans available in system. If plan_service not installed yet, return simple defaults.
    """
    if PLAN_SERVICE_AVAILABLE:
        plans = get_all_plans()
        return [
            {
                "name": p.name,
                "display_name": p.display_name,
                "monthly_price_usd": float(p.monthly_price_usd),
                "daily_search_limit": int(p.daily_search_limit),
                "monthly_credit_allowance": int(p.monthly_credit_allowance or 0),
                "rate_limit_per_sec": int(p.rate_limit_per_sec or 0),
                "is_public": bool(p.is_public)
            } for p in plans
        ]

    # fallback defaults
    return [
        {"name":"free","display_name":"Free","monthly_price_usd":0.0,"daily_search_limit":20,"monthly_credit_allowance":0,"rate_limit_per_sec":1,"is_public":True},
        {"name":"pro","display_name":"Pro","monthly_price_usd":29.0,"daily_search_limit":200,"monthly_credit_allowance":10000,"rate_limit_per_sec":5,"is_public":True},
    ]

@router.post("/seed", dependencies=[Depends(get_current_admin)])
def seed_plans_admin():
    """
    Admin-only: seed default plans into DB. Safe to call multiple times.
    """
    if not PLAN_SERVICE_AVAILABLE:
        raise HTTPException(status_code=501, detail="plan_service_missing")
    try:
        seed_default_plans()
        return {"ok": True}
    except Exception as e:
        logger.exception("seed_default_plans failed")
        raise HTTPException(status_code=500, detail="seed_failed")

@router.post("/assign/{user_id}", dependencies=[Depends(get_current_admin)])
def assign_plan_admin(user_id: int, plan_name: str):
    """
    Admin: assign a plan to a user.
    This delegates to plan_service only for plan existence; actual user update is done here.
    """
    if not PLAN_SERVICE_AVAILABLE:
        raise HTTPException(status_code=501, detail="plan_service_missing")
    db = SessionLocal()
    try:
        User = __import__("backend.app.models.user", fromlist=["User"]).User
        user = db.query(User).get(user_id)
        if not user:
            raise HTTPException(status_code=404, detail="user_not_found")
        plan = get_plan_by_name(plan_name)
        if not plan:
            raise HTTPException(status_code=404, detail="plan_not_found")
        # prefer string `plan` on user; if user has plan_id model adjust accordingly
        try:
            user.plan = plan.name
        except Exception:
            # if no attribute, attempt to set via dict (some ORMs allow)
            setattr(user, "plan", plan.name)
        db.add(user)
        db.commit()
        return {"ok": True, "user_id": user_id, "plan": plan.name}
    finally:
        db.close()
