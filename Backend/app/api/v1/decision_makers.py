# backend/app/api/v1/decision_makers.py
from fastapi import APIRouter, Request, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional, Dict, Any
import uuid
from decimal import Decimal, ROUND_HALF_UP

from backend.app.services.decision_maker_service import search_decision_makers
from backend.app.services.pricing_service import get_cost_for_key
from backend.app.services.credits_service import reserve_and_deduct, add_credits, get_user_balance
from backend.app.services.team_service import is_user_member_of_team
from backend.app.services.plan_service import get_plan_by_name
from backend.app.utils.security import get_current_user

router = APIRouter(prefix="/api/v1/decision-makers", tags=["decision-makers"])


class DecisionSearchIn(BaseModel):
    domain: Optional[str] = None
    company: Optional[str] = None
    max_results: int = 25
    use_cache: bool = True
    team_id: Optional[int] = None  # optional override


def _dec(x) -> Decimal:
    return Decimal(str(x)).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)


@router.post("/search", response_model=Dict[str, Any])
def search(payload: DecisionSearchIn, request: Request, current_user = Depends(get_current_user)):
    """
    Decision Maker Finder (PDL + Apollo)
    With:
    - API Key support
    - Team billing
    - Credits reservation
    - Per-result pricing
    - Refund excess credits
    """

    # ------------------------- USER RESOLUTION -------------------------
    user = current_user
    if not user:
        raise HTTPException(status_code=401, detail="auth_required")

    # ------------------------- TEAM BILLING DECISION -------------------------
    chosen_team = payload.team_id or getattr(request.state, "team_id", None)

    if chosen_team:
        if not is_user_member_of_team(user.id, chosen_team):
            raise HTTPException(status_code=403, detail="not_team_member")

    # ------------------------- INPUT VALIDATION -------------------------
    if not payload.domain and not payload.company:
        raise HTTPException(status_code=400, detail="domain_or_company_required")

    # ------------------------- PLAN LIMITS -------------------------
    if hasattr(user, "plan") and user.plan:
        plan = get_plan_by_name(user.plan)
        if plan and plan.daily_search_limit and payload.max_results > plan.daily_search_limit:
            raise HTTPException(status_code=429, detail="plan_limit_exceeded")

    # ------------------------- PRICING -------------------------
    cost_per = _dec(get_cost_for_key("decision_maker.search_per_result") or 0)
    estimated_cost = (cost_per * Decimal(payload.max_results)).quantize(Decimal("0.000001"))

    job_id = f"dm-{uuid.uuid4().hex[:12]}"
    reserve_ref = f"{job_id}:reserve"

    # ------------------------- RESERVE CREDITS -------------------------
    try:
        reserve_tx = reserve_and_deduct(
            user.id,
            estimated_cost,
            reference=reserve_ref,
            team_id=chosen_team
        )
    except HTTPException as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)

    # ------------------------- RUN SEARCH -------------------------
    try:
        results = search_decision_makers(
            domain=payload.domain,
            company_name=payload.company,
            max_results=payload.max_results,
            use_cache=payload.use_cache,
            caller_api_key=None
        )
    except Exception:
        # On search failure → refund full amount
        if chosen_team:
            from backend.app.services.team_billing_service import add_team_credits
            add_team_credits(chosen_team, estimated_cost, reference=f"{job_id}:refund_error")
        else:
            add_credits(user.id, estimated_cost, reference=f"{job_id}:refund_error")
        raise HTTPException(status_code=500, detail="search_failed")

    # ------------------------- ACTUAL COST & REFUND -------------------------
    actual_count = len(results)
    actual_cost = (cost_per * Decimal(actual_count)).quantize(Decimal("0.000001"))

    refund_amount = (estimated_cost - actual_cost) if actual_cost < estimated_cost else Decimal("0")

    refund_tx = None
    if refund_amount > 0:
        try:
            if chosen_team:
                from backend.app.services.team_billing_service import add_team_credits
                refund_tx = add_team_credits(chosen_team, refund_amount, reference=f"{job_id}:refund")
            else:
                refund_tx = add_credits(user.id, refund_amount, reference=f"{job_id}:refund")
        except Exception:
            refund_tx = {"error": "refund_failed"}

    # ------------------------- RESPONSE -------------------------
    return {
        "job_id": job_id,
        "requested_max_results": payload.max_results,
        "returned_results": actual_count,
        "cost_per_result": float(cost_per),
        "estimated_cost": float(estimated_cost),
        "actual_cost": float(actual_cost),
        "refund_amount": float(refund_amount),
        "reserve_tx": reserve_tx,
        "refund_tx": refund_tx,
        "results": results
    }

# backend/app/api/v1/decision_makers.py
from fastapi import APIRouter, Request, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional, Dict, Any
import uuid
from decimal import Decimal, ROUND_HALF_UP

from backend.app.services.decision_maker_service import search_decision_makers
from backend.app.services.pricing_service import get_cost_for_key
from backend.app.services.credits_service import reserve_and_deduct, add_credits, get_user_balance
from backend.app.services.team_service import is_user_member_of_team
from backend.app.services.team_billing_service import add_team_credits, refund_to_team
from backend.app.services.plan_service import get_plan_by_name
from backend.app.utils.security import get_current_user
from backend.app.db import SessionLocal
from backend.app.models.user import User

router = APIRouter(prefix="/api/v1/decision-makers", tags=["decision-makers"])

class DecisionSearchIn(BaseModel):
    domain: Optional[str] = None
    company: Optional[str] = None
    max_results: int = 25
    use_cache: bool = True
    team_id: Optional[int] = None  # optional override

def _dec(x) -> Decimal:
    return Decimal(str(x)).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)

@router.post("/search", response_model=Dict[str, Any])
def search(payload: DecisionSearchIn, request: Request, current_user = Depends(get_current_user)):
    """
    Decision Maker Finder (PDL + Apollo)
    Team-aware, credits reservation, refund difference for unused results.
    """
    # Resolve user (JWT prioritized; API-key user fallback)
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

    # Input validation
    if not payload.domain and not payload.company:
        raise HTTPException(status_code=400, detail="domain_or_company_required")

    # Determine team context (payload override -> middleware -> None)
    chosen_team = payload.team_id or getattr(request.state, "team_id", None)
    if chosen_team:
        if not is_user_member_of_team(user.id, chosen_team):
            raise HTTPException(status_code=403, detail="not_team_member")

    # Plan enforcement (per-user plan limit on max_results)
    if hasattr(user, "plan") and user.plan:
        plan = get_plan_by_name(user.plan)
        if plan and plan.daily_search_limit and payload.max_results > plan.daily_search_limit:
            raise HTTPException(status_code=429, detail=f"max_results_exceeds_plan_limit ({plan.daily_search_limit})")

    # Pricing & reserve
    cost_per = _dec(get_cost_for_key("decision_maker.search_per_result") or 0)
    estimated_cost = (cost_per * Decimal(payload.max_results)).quantize(Decimal("0.000001"))
    job_id = f"dm-{uuid.uuid4().hex[:12]}"
    reserve_ref = f"{job_id}:reserve"

    try:
        reserve_tx = reserve_and_deduct(user.id, estimated_cost, reference=reserve_ref, team_id=chosen_team)
    except HTTPException as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)

    # Run search (pass caller_api_key if present)
    api_key_row = getattr(request.state, "api_key_row", None)
    caller_api_key = api_key_row.key if api_key_row else None

    try:
        results = search_decision_makers(
            domain=payload.domain,
            company_name=payload.company,
            max_results=payload.max_results,
            use_cache=payload.use_cache,
            caller_api_key=caller_api_key
        )
    except Exception as e:
        # refund full on error
        try:
            if chosen_team:
                refund_to_team(chosen_team, estimated_cost, reference=f"{job_id}:refund_on_error")
            else:
                add_credits(user.id, estimated_cost, reference=f"{job_id}:refund_on_error")
        except Exception:
            pass
        raise HTTPException(status_code=500, detail="decision_search_failed")

    # Compute actual cost (per returned result) and refund difference
    actual_count = len(results or [])
    actual_cost = (cost_per * Decimal(actual_count)).quantize(Decimal("0.000001"))
    refund_amount = (estimated_cost - actual_cost) if actual_cost < estimated_cost else Decimal("0")

    refund_tx = None
    if refund_amount > 0:
        try:
            if chosen_team:
                refund_tx = refund_to_team(chosen_team, refund_amount, reference=f"{job_id}:refund")
            else:
                refund_tx = add_credits(user.id, refund_amount, reference=f"{job_id}:refund")
        except Exception:
            refund_tx = {"error": "refund_failed"}

    return {
        "job_id": job_id,
        "requested_max_results": payload.max_results,
        "returned_results": actual_count,
        "cost_per_result": float(cost_per),
        "estimated_cost": float(estimated_cost),
        "actual_cost": float(actual_cost),
        "refund_amount": float(refund_amount),
        "reserve_tx": reserve_tx,
        "refund_tx": refund_tx,
        "results": results
    }


