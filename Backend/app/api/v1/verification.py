# backend/app/api/v1/verification.py
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from backend.app.utils.security import get_current_user
from backend.app.services.verification_engine import verify_email_sync
from backend.app.services.pricing_service import get_cost_for_key
from backend.app.services.credits_service import reserve_and_deduct
from backend.app.services.team_service import is_user_member_of_team

router = APIRouter()

class VerifyIn(BaseModel):
    email: str
    team_id: int = None  # optional override from frontend

@router.post("/single")
def single_verify(payload: VerifyIn, request: Request, current_user = Depends(get_current_user)):
    """
    Single verify endpoint.
    Billing priority:
      1) if payload.team_id provided -> require membership -> try team pool
      2) else if request.state.team_id set -> try that team pool
      3) else use personal credits
    """
    user = current_user
    # decide team context
    team_id = payload.team_id or getattr(request.state, "team_id", None)

    # validate membership if explicit team_id provided
    if team_id:
        ok = is_user_member_of_team(user.id, team_id)
        if not ok:
            raise HTTPException(status_code=403, detail="not_team_member")

    # pricing and billing
    cost = float(get_cost_for_key("verify.single") or 1.0)
    from decimal import Decimal
    try:
        reserve_and_deduct(user.id, Decimal(str(cost)), reference=f"verify.single:{user.id}", team_id=team_id)
    except HTTPException as e:
        # re-raise for client handling (402 etc)
        raise e

    # run verification
    result = verify_email_sync(payload.email, user_id=user.id)

    # NOTE: you may want to refund on quick failure; for single verifies we treat as consumed
    return {"cost": cost, "result": result}

# backend/app/api/v1/verification.py
from fastapi import APIRouter, Request, Depends, HTTPException
from pydantic import BaseModel
from decimal import Decimal, ROUND_HALF_UP
import uuid
from typing import Dict, Any, Optional

from backend.app.utils.security import get_current_user
from backend.app.services.pricing_service import get_cost_for_key
from backend.app.services.credits_service import reserve_and_deduct, add_credits, get_user_balance
from backend.app.services.plan_service import get_plan_by_name
from backend.app.services.verification_engine import verify_email_sync
from backend.app.services.team_service import is_user_member_of_team
from backend.app.services.team_billing_service import refund_to_team
from backend.app.db import SessionLocal
from backend.app.models.user import User

router = APIRouter(prefix="/api/v1/verify", tags=["verification"])

def _dec(x) -> Decimal:
    return Decimal(str(x)).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)

class VerifyIn(BaseModel):
    email: str
    team_id: Optional[int] = None  # optional override

@router.post("/single", response_model=Dict[str, Any])
def single_verify(payload: VerifyIn, request: Request, current_user = Depends(get_current_user)):
    """
    Single email verification (team-aware).
    Charges: pricing key "verify.single"
    """
    # resolve user
    user = current_user
    if not user:
        api_uid = getattr(request.state, "api_user_id", None)
        if api_uid:
            db = SessionLocal()
            try:
                user = db.query(User).get(int(api_uid))
            finally:
                db.close()
    if not user:
        raise HTTPException(status_code=401, detail="auth_required")

    email = payload.email.strip().lower()
    chosen_team = payload.team_id or getattr(request.state, "team_id", None)
    if chosen_team:
        if not is_user_member_of_team(user.id, chosen_team):
            raise HTTPException(status_code=403, detail="not_team_member")

    # plan check (if any)
    if hasattr(user, "plan") and user.plan:
        plan = get_plan_by_name(user.plan)
        if plan and plan.daily_search_limit and 1 > plan.daily_search_limit:
            raise HTTPException(status_code=429, detail="plan_limit_reached")

    # pricing + reserve
    cost_per = _dec(get_cost_for_key("verify.single") or 0)
    estimated_cost = cost_per
    job_id = f"ver-{uuid.uuid4().hex[:12]}"

    try:
        reserve_tx = reserve_and_deduct(user.id, estimated_cost, reference=f"{job_id}:reserve", team_id=chosen_team)
    except HTTPException as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)

    # run verification
    try:
        result = verify_email_sync(email, user_id=user.id)
    except Exception:
        # refund full on unexpected error
        try:
            if chosen_team:
                refund_to_team(chosen_team, estimated_cost, reference=f"{job_id}:refund_error")
            else:
                add_credits(user.id, estimated_cost, reference=f"{job_id}:refund_error")
        except Exception:
            pass
        raise HTTPException(status_code=500, detail="verification_failed")

    # smart refund policy example
    refund_amount = Decimal("0")
    if result.get("status") == "invalid":
        refund_amount = (estimated_cost * Decimal("0.5")).quantize(Decimal("0.000001"))
        try:
            if chosen_team:
                refund_to_team(chosen_team, refund_amount, reference=f"{job_id}:partial_refund_invalid")
            else:
                add_credits(user.id, refund_amount, reference=f"{job_id}:partial_refund_invalid")
        except Exception:
            pass

    actual_cost = estimated_cost - refund_amount

    return {
        "job_id": job_id,
        "email": email,
        "result": result,
        "estimated_cost": float(estimated_cost),
        "actual_cost": float(actual_cost),
        "refund_amount": float(refund_amount),
        "reserve_tx": reserve_tx
        }



