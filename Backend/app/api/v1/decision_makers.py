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

@router.post("/search", response_model=Dict[str, Any])
def search(payload: DecisionSearchIn, request: Request, current_user = Depends(get_current_user)):
    user = current_user
    if not user:
        raise HTTPException(status_code=401, detail="auth_required")

    caller_api_key = getattr(request.state, "api_key_row", None).key if getattr(request.state, "api_key_row", None) else None
    plan = get_plan_by_name(getattr(user, "plan", None)) if hasattr(user, "plan") else None

    # pricing/reserve
    cost_per_result = Decimal(str(get_cost_for_key("decision_maker.search_per_result") or 0))
    estimated_cost = (cost_per_result * Decimal(payload.max_results)).quantize(Decimal("0.000001"))

    job_id = f"dmjob-{uuid.uuid4().hex[:12]}"
    try:
        reserve_res = reserve_and_deduct(user.id, estimated_cost, reference=f"{job_id}:reserve", job_id=job_id)
    except HTTPException as e:
        raise

    # run search (may call PDL/Apollo)
    try:
        results = search_decision_makers(domain=payload.domain, company_name=payload.company, max_results=payload.max_results, use_cache=payload.use_cache, caller_api_key=caller_api_key)
    except Exception:
        add_credits(user.id, estimated_cost, reference=f"{job_id}:refund_on_error")
        raise HTTPException(status_code=500, detail="decision_search_failed")

    actual_count = len(results or [])
    actual_cost = (cost_per_result * Decimal(actual_count)).quantize(Decimal("0.000001"))

    # refund difference (if any)
    if actual_cost < estimated_cost:
        refund_amount = (estimated_cost - actual_cost).quantize(Decimal("0.000001"))
        from backend.app.services.team_billing_service import add_team_credits as _add_team_credits
        team_id = getattr(request.state, "team_id", None)
        if team_id:
            try:
                _add_team_credits(team_id, refund_amount, reference=f"{job_id}:refund")
            except Exception:
                pass
        else:
            add_credits(user.id, refund_amount, reference=f"{job_id}:refund")

    return {
        "job_id": job_id,
        "returned_results": actual_count,
        "actual_cost": float(actual_cost),
        "refund_amount": float((estimated_cost - actual_cost) if estimated_cost > actual_cost else 0),
        "results": results
}


# backend/app/api/v1/decision_makers.py
from fastapi import APIRouter, Request, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional, Dict, Any
import uuid
from decimal import Decimal, ROUND_HALF_UP

from backend.app.db import SessionLocal
from backend.app.services.decision_maker_service import search_decision_makers
from backend.app.services.pricing_service import get_cost_for_key
from backend.app.services.credits_service import reserve_and_deduct, add_credits, get_user_balance
from backend.app.services.team_billing_service import add_team_credits
from backend.app.services.plan_service import get_plan_by_name
from backend.app.utils.security import get_current_user

router = APIRouter(prefix="/api/v1/decision-makers", tags=["decision-makers"])

def _dec(x) -> Decimal:
    return Decimal(str(x)).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)


class DecisionSearchIn(BaseModel):
    domain: Optional[str] = None
    company: Optional[str] = None
    max_results: int = 25
    use_cache: bool = True
    team_id: Optional[int] = None


@router.post("/search")
def search(payload: DecisionSearchIn, request: Request, current_user = Depends(get_current_user)):
    user = current_user
    if not user:
        raise HTTPException(status_code=401, detail="auth_required")

    chosen_team = payload.team_id or getattr(request.state, "team_id", None)

    # enforce plan daily_search_limit
    if hasattr(user, "plan") and user.plan:
        plan = get_plan_by_name(user.plan)
        if plan and plan.daily_search_limit and payload.max_results > plan.daily_search_limit:
            raise HTTPException(status_code=429, detail=f"max_results_exceeds_plan_limit ({plan.daily_search_limit})")

    cost_per_result = _dec(get_cost_for_key("decision_maker.search_per_result") or 0)
    estimated_cost = (cost_per_result * Decimal(payload.max_results)).quantize(Decimal("0.000001"))

    job_id = f"dmjob-{uuid.uuid4().hex[:12]}"
    reserve_ref = f"{job_id}:reserve"

    # Reserve credits (team-first)
    try:
        reserve_res = reserve_and_deduct(user.id, estimated_cost, reference=reserve_ref, team_id=chosen_team, job_id=job_id)
    except HTTPException as e:
        raise e

    # perform search
    try:
        api_key_row = getattr(request.state, "api_key_row", None)
        caller_api_key = api_key_row.key if api_key_row else None

        results = search_decision_makers(domain=payload.domain, company_name=payload.company, max_results=payload.max_results, use_cache=payload.use_cache, caller_api_key=caller_api_key)
    except Exception as e:
        # refund on error
        try:
            add_credits(user.id, estimated_cost, reference=f"{job_id}:refund_on_error")
        except Exception:
            pass
        raise HTTPException(status_code=500, detail="decision_search_failed")

    actual_count = len(results or [])
    actual_cost = (cost_per_result * Decimal(actual_count)).quantize(Decimal("0.000001"))
    refund_amount = (estimated_cost - actual_cost).quantize(Decimal("0.000001")) if estimated_cost > actual_cost else Decimal("0")

    # issue refund to team or user accordingly
    if refund_amount > 0:
        if chosen_team:
            try:
                add_team_credits(chosen_team, refund_amount, reference=f"{job_id}:refund")
            except Exception:
                # best-effort: if team refund fails, refund to user
                try:
                    add_credits(user.id, refund_amount, reference=f"{job_id}:refund_fallback")
                except Exception:
                    pass
        else:
            try:
                add_credits(user.id, refund_amount, reference=f"{job_id}:refund")
            except Exception:
                pass

    return {
        "job_id": job_id,
        "requested_max_results": payload.max_results,
        "returned_results": actual_count,
        "cost_per_result": float(cost_per_result),
        "estimated_cost": float(estimated_cost),
        "actual_cost": float(actual_cost),
        "refund_amount": float(refund_amount),
        "results": results,
        "reserve_tx": reserve_res,
    }


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
from backend.app.services.team_service import is_user_member_of_team
from backend.app.utils.security import get_current_user

router = APIRouter(prefix="/api/v1/decision-makers", tags=["decision-makers"])

def _decimal(x) -> Decimal:
    return Decimal(str(x)).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)

class DecisionSearchIn(BaseModel):
    domain: Optional[str] = None
    company: Optional[str] = None
    max_results: int = 25
    use_cache: bool = True

@router.post("/search")
def search(payload: DecisionSearchIn, request: Request, current_user = Depends(get_current_user)):
    """
    Decision Maker Finder endpoint with team billing + reservation + refunds.
    """
    user = current_user
    if not user:
        raise HTTPException(status_code=401, detail="auth_required")

    chosen_team = getattr(request.state, "team_id", None)

    # if client passed team_id in payload (not recommended) - validate same
    if hasattr(payload, "team_id") and getattr(payload, "team_id", None):
        chosen_team = getattr(payload, "team_id")

    if chosen_team:
        if not is_user_member_of_team(user.id, chosen_team):
            raise HTTPException(status_code=403, detail="not_team_member")

    # enforce plan limit on max_results
    if hasattr(user, "plan") and user.plan:
        plan = get_plan_by_name(user.plan)
        if plan and plan.daily_search_limit and payload.max_results > plan.daily_search_limit:
            raise HTTPException(status_code=429, detail=f"max_results_exceeds_plan_limit ({plan.daily_search_limit})")

    # pricing
    cost_per_result = _decimal(get_cost_for_key("decision_maker.search_per_result") or 0)
    estimated_cost = (cost_per_result * Decimal(payload.max_results)).quantize(Decimal("0.000001"))

    job_id = f"dmjob-{uuid.uuid4().hex[:12]}"
    reserve_ref = f"{job_id}:reserve"

    # reserve credits team-first
    try:
        reserve_tx = reserve_and_deduct(user.id, estimated_cost, reference=reserve_ref, team_id=chosen_team, job_id=job_id) if estimated_cost > 0 else {"balance_after": float(get_user_balance(user.id))}
    except HTTPException as e:
        # pass through 402 to client
        raise HTTPException(status_code=e.status_code, detail=e.detail)

    # perform search (uses configured external clients inside search_decision_makers)
    try:
        # Pass caller_api_key if present (API-key middleware may attach api_key_row)
        api_key_row = getattr(request.state, "api_key_row", None)
        caller_api_key = api_key_row.key if api_key_row else None

        results = search_decision_makers(domain=payload.domain, company_name=payload.company, max_results=payload.max_results, use_cache=payload.use_cache, caller_api_key=caller_api_key)
    except Exception as e:
        # refund on error
        try:
            add_credits(user.id, estimated_cost, reference=f"{job_id}:refund_on_error")
        except Exception:
            pass
        raise HTTPException(status_code=500, detail="decision_search_failed")

    # calculate actual cost & refund difference
    actual_count = len(results or [])
    actual_cost = (cost_per_result * Decimal(actual_count)).quantize(Decimal("0.000001"))
    refund_amount = (estimated_cost - actual_cost).quantize(Decimal("0.000001")) if estimated_cost > actual_cost else Decimal("0")

    refund_tx = None
    if refund_amount > 0:
        try:
            add_credits(user.id, refund_amount, reference=f"{job_id}:refund")
            refund_tx = {"refunded": float(refund_amount)}
        except Exception:
            refund_tx = {"error": "refund_failed"}

    response = {
        "job_id": job_id,
        "requested_max_results": payload.max_results,
        "returned_results": actual_count,
        "cost_per_result": float(cost_per_result),
        "estimated_cost": float(estimated_cost),
        "actual_cost": float(actual_cost),
        "refund_amount": float(refund_amount),
        "results": results,
        "reserve_tx": reserve_tx,
        "refund_tx": refund_tx,
    }
    return response



# backend/app/api/v1/decision_makers.py
import uuid
import logging
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional, Dict, Any

from fastapi import APIRouter, Request, Depends, HTTPException
from pydantic import BaseModel

from backend.app.db import SessionLocal
from backend.app.models.credit_reservation import CreditReservation
from backend.app.services.decision_maker_service import search_decision_makers
from backend.app.services.pricing_service import get_cost_for_key
from backend.app.services.credits_service import (
    reserve_and_deduct,
    add_credits,
    get_user_balance,
    capture_reservation_and_charge,
    release_reservation,
)
from backend.app.services.plan_service import get_plan_by_name
from backend.app.utils.security import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/decision-makers", tags=["decision-makers"])

# Request schema
class DecisionSearchIn(BaseModel):
    domain: Optional[str] = None
    company: Optional[str] = None
    max_results: int = 25
    use_cache: bool = True

def _dec(x) -> Decimal:
    return Decimal(str(x)).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)

@router.post("/search")
def search(payload: DecisionSearchIn, request: Request, current_user = Depends(get_current_user)) -> Dict[str, Any]:
    """
    Decision Maker Finder with safe billing:
    - Reserves credits up-front (team-first if team_id present)
    - Runs PDL/Apollo + pattern engine (search_decision_makers)
    - Calculates actual cost (cost_per_result * returned_count)
    - Captures reservations equal to actual_cost, refunds remainder
    - Returns results + billing details
    """

    # ---------- auth / user resolve ----------
    user = current_user
    if not user:
        # try API-key provided user id (middleware may set request.state.api_user_id)
        api_uid = getattr(request.state, "api_user_id", None)
        if api_uid:
            db = SessionLocal()
            try:
                user = db.query(__import__("backend.app.models.user", fromlist=["User"]).User).get(int(api_uid))
            finally:
                db.close()
    if not user:
        raise HTTPException(status_code=401, detail="auth_required")

    # ---------- validate input ----------
    if not payload.domain and not payload.company:
        raise HTTPException(status_code=400, detail="domain_or_company_required")

    # ---------- plan limit check ----------
    if hasattr(user, "plan") and user.plan:
        plan = get_plan_by_name(user.plan)
        if plan and plan.daily_search_limit and payload.max_results > plan.daily_search_limit:
            raise HTTPException(status_code=429, detail=f"max_results_exceeds_plan_limit({plan.daily_search_limit})")

    # ---------- team context (optional) ----------
    chosen_team = getattr(request.state, "team_id", None)
    # frontend may send ?team_id=..., middleware might already set request.state.team_id
    if request.query_params.get("team_id"):
        try:
            chosen_team = int(request.query_params.get("team_id"))
        except Exception:
            chosen_team = chosen_team

    # ---------- pricing & reservation ----------
    cost_per_result = _dec(get_cost_for_key("decision_maker.search_per_result") or 0)
    estimated_cost = (cost_per_result * Decimal(payload.max_results)).quantize(Decimal("0.000001"))

    job_id = f"dmjob-{uuid.uuid4().hex[:12]}"
    reserve_ref = f"{job_id}:reserve"

    try:
        # reserve_and_deduct will try team pool first (if team_id provided) then user balance
        reserve_res = reserve_and_deduct(
            user.id,
            estimated_cost,
            reference=reserve_ref,
            team_id=chosen_team,
            job_id=job_id
        )
    except HTTPException as e:
        # bubble up 402 insufficient_credits or 403 not allowed
        raise HTTPException(status_code=e.status_code, detail=e.detail)
    except Exception as e:
        logger.exception("reservation failed for decision search: %s", e)
        raise HTTPException(status_code=500, detail="reservation_failed")

    # ---------- perform search ----------
    try:
        caller_api_key = getattr(request.state, "api_key", None) or None
        results = search_decision_makers(
            domain=payload.domain,
            company_name=payload.company,
            max_results=payload.max_results,
            use_cache=payload.use_cache,
            caller_api_key=caller_api_key
        )
    except Exception as e:
        # refund on internal failure
        try:
            add_credits(user.id, estimated_cost, reference=f"{job_id}:refund_on_error")
        except Exception:
            logger.exception("refund on search error failed")
        logger.exception("decision search failed: %s", e)
        raise HTTPException(status_code=500, detail="decision_search_failed")

    # ---------- determine actual cost & refund difference ----------
    actual_count = len(results or [])
    actual_cost = (cost_per_result * Decimal(actual_count)).quantize(Decimal("0.000001"))
    refund_amount = (estimated_cost - actual_cost).quantize(Decimal("0.000001")) if estimated_cost > actual_cost else Decimal("0")

    # ---------- finalize reservations: capture or refund ----------
    db = SessionLocal()
    try:
        # fetch reservations linked to this job
        reservations = db.query(CreditReservation).filter(
            CreditReservation.job_id == job_id,
            CreditReservation.locked == True
        ).all()

        remaining_to_charge = actual_cost

        for r in reservations:
            if remaining_to_charge <= 0:
                # release remaining reservation (unused)
                try:
                    release_reservation(db, r.id)
                except Exception:
                    logger.exception("release reservation failed id=%s", r.id)
                continue

            r_amt = Decimal(str(r.amount))

            if r_amt <= remaining_to_charge:
                # capture full reservation
                try:
                    capture_reservation_and_charge(db, r.id, type_="decision.charge", reference=f"{job_id}:charge")
                except Exception:
                    logger.exception("capture reservation failed id=%s", r.id)
                remaining_to_charge -= r_amt
            else:
                # capture reservation (we capture full reservation and refund extra portion back)
                try:
                    capture_reservation_and_charge(db, r.id, type_="decision.charge", reference=f"{job_id}:charge")
                except Exception:
                    logger.exception("capture reservation failed id=%s", r.id)
                extra = r_amt - remaining_to_charge
                # refund extra back to user or team
                try:
                    # If reservation belonged to a team, ideally refund to team pool.
                    # For simplicity we refund to user; adapt to team flow if you implemented team transactions.
                    add_credits(user.id, extra, reference=f"{job_id}:refund_extra")
                except Exception:
                    logger.exception("refund extra failed for job %s", job_id)
                remaining_to_charge = Decimal("0")
    except Exception:
        logger.exception("reservation finalize error for dm job %s", job_id)
    finally:
        db.close()

    # If we still computed refund_amount (estimated - actual) and no reservations found (fallback), credit user
    if refund_amount > 0 and not reservations:
        try:
            add_credits(user.id, refund_amount, reference=f"{job_id}:refund_fallback")
        except Exception:
            logger.exception("fallback refund failed for job %s", job_id)

    # ---------- response ----------
    return {
        "job_id": job_id,
        "requested_max_results": payload.max_results,
        "returned_results": actual_count,
        "cost_per_result": float(cost_per_result),
        "estimated_cost": float(estimated_cost),
        "actual_cost": float(actual_cost),
        "refund_amount": float(refund_amount),
        "results": results,
        "reserve_tx": reserve_res,
}
