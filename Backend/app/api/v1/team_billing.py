from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from decimal import Decimal
from backend.app.services.team_billing_service import (
    get_team_balance, ensure_team_balance_row, add_team_credits, list_team_transactions, transfer_team_to_user
)
from backend.app.services.team_service import get_team
from backend.app.utils.security import get_current_user
from backend.app.services.team_service import get_member_role
from backend.app.services.credits_service import add_credits as user_add_credits
from backend.app.services.acl_check import require_team_permission

router = APIRouter(prefix="/api/v1/team-billing", tags=["team-billing"])

class TopupIn(BaseModel):
    team_id: int
    amount: float
    reference: str = None

class TransferIn(BaseModel):
    team_id: int
    user_id: int
    amount: float
    reference: str = None

@router.get("/balance/{team_id}")
def api_team_balance(team_id: int, current_user = Depends(get_current_user)):
    # membership required to view
    role = get_member_role(current_user.id, team_id)
    if not role:
        raise HTTPException(status_code=403, detail="not_team_member")
    bal = get_team_balance(team_id)
    return {"team_id": team_id, "balance": float(bal)}

@router.post("/topup")
def api_topup(payload: TopupIn, request: Request, current_user = Depends(get_current_user)):
    # require owner or admin to topup (owner usually does via payment)
    role = get_member_role(current_user.id, payload.team_id)
    if role not in ("owner", "admin"):
        raise HTTPException(status_code=403, detail="only_owner_or_admin")

    # In real world, you will implement Stripe/UPI payment flow and on success call add_team_credits
    res = add_team_credits(payload.team_id, Decimal(str(payload.amount)), reference=payload.reference)
    return {"ok": True, "team_id": payload.team_id, "balance_after": res["balance_after"], "tx": res["transaction_id"]}

@router.post("/transfer-to-user")
def api_transfer_to_user(payload: TransferIn, request: Request, current_user = Depends(get_current_user)):
    # only owner/admin allowed to move credits out
    role = get_member_role(current_user.id, payload.team_id)
    if role not in ("owner", "admin"):
        raise HTTPException(status_code=403, detail="only_owner_or_admin")
    # perform team transfer out
    try:
        transfer_meta = transfer_team_to_user(payload.team_id, payload.user_id, Decimal(str(payload.amount)), reference=payload.reference)
    except HTTPException as e:
        raise e
    # now add to user account
    user_add_credits(payload.user_id, Decimal(str(payload.amount)), reference=f"team_transfer_in:{payload.team_id}")
    return {"ok": True, "transfer_tx": transfer_meta["transaction_id"], "balance_after": transfer_meta["balance_after"]}

@router.get("/transactions/{team_id}")
def api_team_transactions(team_id: int, current_user = Depends(get_current_user)):
    role = get_member_role(current_user.id, team_id)
    if not role:
        raise HTTPException(status_code=403, detail="not_team_member")
    rows = list_team_transactions(team_id)
    out = []
    for r in rows:
        out.append({
            "id": r.id,
            "amount": float(r.amount),
            "balance_after": float(r.balance_after),
            "type": r.type,
            "reference": r.reference,
            "created_at": str(r.created_at)
        })
    return {"team_id": team_id, "transactions": out}
