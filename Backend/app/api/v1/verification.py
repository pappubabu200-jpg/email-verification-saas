# backend/app/api/v1/verification.py

import io
import uuid
import csv
import zipfile
import logging
from decimal import Decimal, ROUND_HALF_UP
from typing import List, Dict, Any, Optional

from fastapi import APIRouter, Request, Depends, UploadFile, File, HTTPException
from pydantic import BaseModel

from backend.app.utils.security import get_current_user
from backend.app.services.verification_engine import verify_email_sync
from backend.app.services.pricing_service import get_cost_for_key
from backend.app.services.credits_service import reserve_and_deduct, add_credits, get_user_balance
from backend.app.services.plan_service import get_plan_by_name

router = APIRouter(prefix="/api/v1/verify", tags=["verification"])
logger = logging.getLogger(__name__)

def _dec(x) -> Decimal:
    return Decimal(str(x)).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)

class VerifyPayload(BaseModel):
    email: str


# ---------------------------------------------
# SINGLE VERIFICATION
# ---------------------------------------------
@router.post("/single", response_model=Dict[str, Any])
def single_verify(payload: VerifyPayload, request: Request, current_user=Depends(get_current_user)):

    user = current_user
    if not user:
        raise HTTPException(status_code=401, detail="auth_required")

    email = payload.email.strip().lower()

    # PLAN ENFORCEMENT
    plan = get_plan_by_name(user.plan) if hasattr(user, "plan") else None
    if plan and plan.daily_search_limit and 1 > plan.daily_search_limit:
        raise HTTPException(status_code=429, detail="plan_limit_reached")

    # PRICING
    cost_per = _dec(get_cost_for_key("verify.single"))
    estimated_cost = cost_per
    job_id = f"ver-{uuid.uuid4().hex[:12]}"

    # RESERVE CREDITS
    try:
        reserve_res = reserve_and_deduct(user.id, estimated_cost, reference=f"{job_id}:reserve")
    except HTTPException as e:
        raise e

    # DO VERIFICATION
    try:
        result = verify_email_sync(email, user_id=user.id)
    except Exception as e:
        # refund full on error
        try:
            add_credits(user.id, estimated_cost, reference=f"{job_id}:refund_error")
        except:
            pass
        raise HTTPException(status_code=500, detail="verification_failed")

    # SMART REFUND POLICY
    refund_amount = Decimal("0")
    if result.get("status") == "invalid":
        refund_amount = (estimated_cost * Decimal("0.5")).quantize(Decimal("0.000001"))
        try:
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
        "reserve_tx": reserve_res
    }


# --------------------------------------------------------------
# BULK PARSER HELPERS
# --------------------------------------------------------------
def parse_csv(content: str) -> List[str]:
    urls = []
    reader = csv.reader(io.StringIO(content))
    for row in reader:
        for col in row:
            c = col.strip()
            if c:
                urls.append(c)
                break
    return urls


def parse_zip(content: bytes) -> List[str]:
    emails = []
    z = zipfile.ZipFile(io.BytesIO(content))
    for name in z.namelist():
        if name.endswith("/") or name.startswith("__MACOSX"):
            continue
        if name.lower().endswith(".csv"):
            raw = z.read(name).decode("utf-8", errors="ignore")
            emails.extend(parse_csv(raw))
        elif name.lower().endswith(".txt"):
            txt = z.read(name).decode("utf-8", errors="ignore")
            for line in txt.splitlines():
                if line.strip():
                    emails.append(line.strip())
    return emails


# ---------------------------------------------
# BULK VERIFICATION
# ---------------------------------------------
@router.post("/bulk-upload")
async def bulk_verify(file: UploadFile = File(...), current_user=Depends(get_current_user)):

    user = current_user
    if not user:
        raise HTTPException(status_code=401, detail="auth_required")

    filename = file.filename.lower()
    content = await file.read()

    # FILE TYPE PARSE
    emails: List[str] = []

    if filename.endswith(".zip"):
        emails = parse_zip(content)
    elif filename.endswith(".csv"):
        emails = parse_csv(content.decode("utf-8", errors="ignore"))
    else:
        raw = content.decode("utf-8", errors="ignore")
        emails = [line.strip() for line in raw.splitlines() if line.strip()]

    # CLEAN + DEDUPE
    emails = [e.lower().strip() for e in emails if "@" in e]
    emails = list(dict.fromkeys(emails))

    total = len(emails)
    if total == 0:
        raise HTTPException(status_code=400, detail="no_valid_emails")

    # PLAN LIMIT
    plan = get_plan_by_name(user.plan) if hasattr(user, "plan") else None
    if plan and plan.daily_search_limit and total > plan.daily_search_limit:
        raise HTTPException(status_code=429, detail=f"plan_limit_exceeded({plan.daily_search_limit})")

    # PRICING
    cost_per = _dec(get_cost_for_key("verify.bulk_per_email"))
    estimated_cost = (cost_per * Decimal(total)).quantize(Decimal("0.000001"))

    job_id = f"bulk-ver-{uuid.uuid4().hex[:12]}"

    # RESERVE
    try:
        reserve_res = reserve_and_deduct(user.id, estimated_cost, reference=f"{job_id}:reserve")
    except HTTPException as e:
        raise e

    # PROCESS SYNC (for now)
    results = []
    valid = 0

    for e in emails:
        try:
            r = verify_email_sync(e, user_id=user.id)
            results.append({"email": e, "result": r})
            if r.get("status") == "valid":
                valid += 1
        except Exception:
            results.append({"email": e, "error": "verify_failed"})

    # SMART BULK REFUND
    refund_amount = Decimal("0")

    invalid_ratio = (total - valid) / total
    if invalid_ratio >= 0.5:
        refund_amount = (estimated_cost * Decimal("0.4")).quantize(Decimal("0.000001"))
        try:
            add_credits(user.id, refund_amount, reference=f"{job_id}:bulk_refund_invalid")
        except:
            pass

    actual_cost = estimated_cost - refund_amount

    return {
        "job_id": job_id,
        "total": total,
        "valid": valid,
        "invalid": total - valid,
        "estimated_cost": float(estimated_cost),
        "actual_cost": float(actual_cost),
        "refund_amount": float(refund_amount),
        "reserve_tx": reserve_res,
        "results_preview": results[:200]
  }
