from fastapi import APIRouter, Depends, HTTPException
from backend.app.services.plan_service import get_all_plans, get_plan_by_name
from backend.app.utils.security import get_current_admin
from backend.app.db import SessionLocal
from backend.app.models.user import User

router = APIRouter(prefix="/api/v1/billing", tags=["billing"])

@router.get("/plans")
def list_plans():
    plans = get_all_plans()
    return [{"name": p.name, "display_name": p.display_name, "monthly_price_usd": float(p.monthly_price_usd), "daily_search_limit": p.daily_search_limit} for p in plans]

@router.post("/users/{user_id}/assign-plan")
def assign_plan(user_id: int, plan_name: str, admin = Depends(get_current_admin)):
    db = SessionLocal()
    try:
        user = db.query(User).get(user_id)
        if not user:
            raise HTTPException(status_code=404, detail="user_not_found")
        plan = get_plan_by_name(plan_name)
        if not plan:
            raise HTTPException(status_code=404, detail="plan_not_found")
        # Set plan on user. You must have user.plan or user.plan_id column. We use user.plan string if available.
        if hasattr(user, "plan"):
            user.plan = plan.name
        else:
            # add plan_name field to user if not present is needed (migration)
            user.plan = plan.name
        db.add(user)
        db.commit()
        return {"ok": True, "user_id": user.id, "plan": plan.name}
    finally:
        db.close()
