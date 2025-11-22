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
