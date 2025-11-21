from fastapi import APIRouter, Query, Depends, HTTPException, Request
from typing import Optional
from backend.app.utils.security import get_current_user
from backend.app.services.decision_maker_service import search_decision_makers
from backend.app.services.decision_quota import check_and_consume, get_usage

router = APIRouter(prefix="/v1/decision-makers", tags=["Decision Makers"])


@router.get("/search")
def search(domain: Optional[str] = Query(None), company: Optional[str] = Query(None),
           max_results: int = Query(25, ge=1, le=200),
           request: Request = None,
           current_user = Depends(get_current_user)):
    """
    Search decision makers by domain or company name.
    Authenticated users only (or support API keys via middleware).
    Enforces per-user daily quota (consumes 1 unit per search).
    """

    # Determine effective user:
    # If API key used, middleware sets request.state.api_user_id
    # We prefer DB user object (current_user). If current_user is None and api_user_id present,
    # you may load user from DB instead. For now we require current_user.
    user = current_user

    if not domain and not company:
        raise HTTPException(status_code=400, detail="domain_or_company_required")

    # Check and consume quota (1 unit per search)
    try:
        used_after, limit = check_and_consume(user, amount=1)
    except HTTPException as e:
        # quota exceeded or auth problems
        raise e

    # Run the actual search (heavy work)
    results = search_decision_makers(domain=domain, company_name=company, max_results=max_results)

    return {
        "query": domain or company,
        "count": len(results),
        "results": results,
        "quota": {"used": used_after, "limit": limit}
                            }


from fastapi import APIRouter, Query, Depends, HTTPException, Request
from typing import Optional

from backend.app.utils.security import get_current_user
from backend.app.services.decision_maker_service import search_decision_makers
from backend.app.services.decision_quota import check_and_consume, get_usage

from backend.app.db import SessionLocal
from backend.app.models.user import User

router = APIRouter(prefix="/v1/decision-makers", tags=["Decision Makers"])


@router.get("/search")
def search(
    domain: Optional[str] = Query(None),
    company: Optional[str] = Query(None),
    max_results: int = Query(25, ge=1, le=200),
    request: Request = None,
    current_user = Depends(get_current_user),   # JWT OR None (API key case)
):
    """
    Decision Maker Finder (PDL + Apollo + Pattern Engine)
    Supports:
    - JWT auth
    - API Key auth (via ApiKeyGuard middleware)

    Enforces per-user daily quota.
    """

    # -----------------------------
    # 🔥 STEP 1: Resolve User (JWT or API Key)
    # -----------------------------
    user = current_user

    if not user:
        # API Key user lookup
        api_uid = getattr(request.state, "api_user_id", None)
        if api_uid:
            db = SessionLocal()
            try:
                user = db.query(User).get(int(api_uid))
            finally:
                db.close()

    if not user:
        raise HTTPException(status_code=401, detail="user_not_found")

    # -----------------------------
    # 🔥 STEP 2: Validate Input
    # -----------------------------
    if not domain and not company:
        raise HTTPException(status_code=400, detail="domain_or_company_required")

    # -----------------------------
    # 🔥 STEP 3: Enforce Quota
    # -----------------------------
    try:
        used_after, limit = check_and_consume(user, amount=1)
    except HTTPException as e:
        raise e   # quota exceeded or auth error

    # -----------------------------
    # 🔥 STEP 4: Run Decision Maker Search
    # -----------------------------
    results = search_decision_makers(
        domain=domain,
        company_name=company,
        max_results=max_results
    )

    # -----------------------------
    # 🔥 STEP 5: Return Response
    # -----------------------------
    return {
        "query": domain or company,
        "count": len(results),
        "results": results,
        "quota": {
            "used": used_after,
            "limit": limit
        }
               }
from fastapi import Depends, APIRouter, Request
from backend.app.services.decision_maker_service import search_decision_makers

router = APIRouter(prefix="/api/v1/decision-makers")

@router.post("/find")
def find_dm(payload: dict, request: Request):
    domain = payload.get("domain")
    company = payload.get("company")

    api_key = None
    if hasattr(request.state, "api_key_row") and request.state.api_key_row:
        api_key = request.state.api_key_row.key

    return search_decision_makers(
        domain=domain,
        company_name=company,
        max_results=25,
        caller_api_key=api_key,
    )


# backend/app/api/v1/decision_makers.py
from fastapi import APIRouter, Request, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
import uuid
from decimal import Decimal, ROUND_HALF_UP
from backend.app.db import SessionLocal
from backend.app.services.decision_maker_service import search_decision_makers
from backend.app.services.pricing_service import get_cost_for_key
from backend.app.services.credits_service import reserve_and_deduct, add_credits, get_user_balance
from backend.app.services.plan_service import get_plan_by_name
from backend.app.utils.security import get_current_user, get_current_admin

router = APIRouter(prefix="/api/v1/decision-makers", tags=["decision-makers"])

# Request model
class DecisionSearchIn(BaseModel):
    domain: Optional[str] = None
    company: Optional[str] = None
    max_results: int = 25
    use_cache: bool = True

# Response model (informal)
class DecisionPersonOut(BaseModel):
    first_name: Optional[str]
    last_name: Optional[str]
    title: Optional[str]
    email: Optional[str]
    company: Optional[str]
    domain: Optional[str]
    source: Optional[str]
    verified: Optional[bool]
    verified_result: Optional[Dict[str, Any]]

def _decimal(x) -> Decimal:
    return Decimal(str(x)).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)

@router.post("/search", response_model=Dict[str, Any])
def search(payload: DecisionSearchIn, request: Request, current_user = Depends(get_current_user)):
    """
    Search decision makers (PDL + Apollo fallback) with pricing + credits reservation.
    Billing rules:
      - cost per result = pricing_service.get_cost_for_key("decision_maker.search_per_result")
      - we reserve cost_per_result * max_results up-front, then refund difference for unused results
    """
    user = current_user
    if not user:
        raise HTTPException(status_code=401, detail="auth_required")

    # determine API key (if present)
    api_key_row = getattr(request.state, "api_key_row", None)
    caller_api_key = api_key_row.key if api_key_row else None

    # enforce plan daily_search_limit (if applicable)
    if hasattr(user, "plan") and user.plan:
        plan = get_plan_by_name(user.plan)
        if plan and plan.daily_search_limit:
            if payload.max_results > plan.daily_search_limit:
                raise HTTPException(status_code=429, detail=f"max_results_exceeds_plan_limit ({plan.daily_search_limit})")

    # pricing
    cost_per_result = Decimal(str(get_cost_for_key("decision_maker.search_per_result") or 0))
    estimated_cost = (cost_per_result * Decimal(payload.max_results)).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)

    # reserve credits upfront
    job_id = f"dmjob-{uuid.uuid4().hex[:12]}"
    reserve_ref = f"{job_id}:reserve"
    try:
        reserve_res = reserve_and_deduct(user.id, estimated_cost, reference=reserve_ref) if estimated_cost > 0 else {"balance_after": float(get_user_balance(user.id))}
    except HTTPException as e:
        # pass through 402 for client to top-up
        raise HTTPException(status_code=e.status_code, detail=e.detail)

    # perform search
    try:
        results = search_decision_makers(domain=payload.domain, company_name=payload.company, max_results=payload.max_results, use_cache=payload.use_cache, caller_api_key=caller_api_key)
    except Exception as e:
        # in case of internal failure, refund full estimated amount
        try:
            add_credits(user.id, estimated_cost, reference=f"{job_id}:refund_on_error")
        except Exception:
            pass
        raise HTTPException(status_code=500, detail="decision_search_failed")

    # determine actual usage cost: charge per result returned
    actual_count = len(results or [])
    actual_cost = (cost_per_result * Decimal(actual_count)).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)

    # refund difference if any (estimated_cost - actual_cost)
    refund_amount = (estimated_cost - actual_cost).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP) if estimated_cost > actual_cost else Decimal("0")
    refund_tx = None
    if refund_amount > 0:
        try:
            refund_tx = add_credits(user.id, refund_amount, reference=f"{job_id}:refund")
        except Exception:
            # If refund fails, write a log and continue (do not break user flow)
            refund_tx = {"error": "refund_failed"}

    # Prepare response with billing details
    response = {
        "job_id": job_id,
        "requested_max_results": payload.max_results,
        "returned_results": actual_count,
        "cost_per_result": float(cost_per_result),
        "estimated_cost": float(estimated_cost),
        "actual_cost": float(actual_cost),
        "refund_amount": float(refund_amount),
        "results": results,
        "reserve_tx": reserve_res,
        "refund_tx": refund_tx,
    }

    return response
