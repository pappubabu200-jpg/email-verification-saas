# backend/app/api/v1/decision_makers.py

import uuid
import logging
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional, Dict, Any
from fastapi import APIRouter, Request, Depends, HTTPException
from pydantic import BaseModel

from backend.app.db import SessionLocal
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
from backend.app.services.team_service import is_user_member_of_team
from backend.app.services.team_billing_service import (
    add_team_credits,
    refund_to_team,
)
from backend.app.utils.security import get_current_user
from backend.app.models.user import User
from backend.app.models.credit_reservation import CreditReservation

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/decision-makers", tags=["decision-makers"])

# Utilities
def _dec(x) -> Decimal:
    return Decimal(str(x)).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)

# Pydantic input schema
class DecisionSearchIn(BaseModel):
    domain: Optional[str] = None
    company: Optional[str] = None
    max_results: int = 25
    use_cache: bool = True
    team_id: Optional[int] = None

@router.post("/search", response_model=Dict[str, Any])
def search(payload: DecisionSearchIn, request: Request, current_user=Depends(get_current_user)) -> Dict[str, Any]:
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
        # Try API key provided user ID (middleware may set request.state.api_user_id)
        api_uid = getattr(request.state, "api_user_id", None)
        if api_uid:
            db = SessionLocal()
            try:
                user = db.query(User).get(int(api_uid))
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
            raise HTTPException(
                status_code=429,
                detail=f"max_results_exceeds_plan_limit({plan.daily_search_limit})"
            )

    # ---------- team context (optional) ----------
    chosen_team = payload.team_id or getattr(request.state, "team_id", None)
    if chosen_team:
        if not is_user_member_of_team(user.id, chosen_team):
            raise HTTPException(status_code=403, detail="not_team_member")

    # ---------- pricing & reservation ----------
    cost_per_result = _dec(get_cost_for_key("decision_maker.search_per_result") or 0)
    estimated_cost = (cost_per_result * Decimal(payload.max_results)).quantize(Decimal("0.000001"))
    job_id = f"dmjob-{uuid.uuid4().hex[:12]}"
    reserve_ref = f"{job_id}:reserve"

    try:
        reserve_res = reserve_and_deduct(
            user.id,
            estimated_cost,
            reference=reserve_ref,
            team_id=chosen_team,
            job_id=job_id
        )
    except HTTPException as e:
        # Bubble up 402 insufficient_credits or 403 not allowed
        raise HTTPException(status_code=e.status_code, detail=e.detail)
    except Exception as e:
        logger.exception("reservation failed for decision search: %s", e)
        raise HTTPException(status_code=500, detail="reservation_failed")

    # ---------- perform search ----------
    try:
        api_key_row = getattr(request.state, "api_key_row", None)
        caller_api_key = api_key_row.key if api_key_row else None
        results = search_decision_makers(
            domain=payload.domain,
            company_name=payload.company,
            max_results=payload.max_results,
            use_cache=payload.use_cache,
            caller_api_key=caller_api_key
        )
    except Exception as e:
        # Refund on internal failure
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
    refund_tx = None

    # ---------- finalize reservations: capture or refund ----------
    db = SessionLocal()
    try:
        # Fetch reservations linked to this job
        reservations = db.query(CreditReservation).filter(
            CreditReservation.job_id == job_id,
            CreditReservation.locked == True
        ).all()
        remaining_to_charge = actual_cost
        for r in reservations:
            if remaining_to_charge <= 0:
                try:
                    release_reservation(db, r.id)
                except Exception:
                    logger.exception("release reservation failed id=%s", r.id)
                continue
            r_amt = Decimal(str(r.amount))
            if r_amt <= remaining_to_charge:
                try:
                    capture_reservation_and_charge(db, r.id, type_="decision.charge", reference=f"{job_id}:charge")
                except Exception:
                    logger.exception("capture reservation failed id=%s", r.id)
                remaining_to_charge -= r_amt
            else:
                try:
                    capture_reservation_and_charge(db, r.id, type_="decision.charge", reference=f"{job_id}:charge")
                except Exception:
                    logger.exception("capture reservation failed id=%s", r.id)
                extra = r_amt - remaining_to_charge
                try:
                    add_credits(user.id, extra, reference=f"{job_id}:refund_extra")
                except Exception:
                    logger.exception("refund extra failed for job %s", job_id)
                remaining_to_charge = Decimal("0")
    except Exception:
        logger.exception("reservation finalize error for dm job %s", job_id)
    finally:
        db.close()

    # Fallback refund if no reservations found
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
        "refund_tx": refund_tx,
    }

reserve_res = reserve_and_deduct(user.id, estimated_cost, reference=reserve_ref, team_id=chosen_team, job_id=job_id)

