from fastapi import APIRouter, Depends, HTTPException
from decimal import Decimal
from backend.app.utils.security import get_current_admin
from backend.app.services.team_billing_service import add_team_credits
from backend.app.services.team_service import create_team, add_member

router = APIRouter(prefix="/api/v1/admin/team", tags=["admin-team"])

@router.post("/topup")
def topup_team(team_id: int, amount: float, ref: str = None, admin=Depends(get_current_admin)):
    tx = add_team_credits(team_id, Decimal(str(amount)), reference=ref)
    return {"ok": True, "tx": tx}

@router.post("/create")
def create_team_admin(owner_id: int, name: str, slug: str = None, admin=Depends(get_current_admin)):
    team = create_team(owner_id, name, slug)
    return {"team_id": team.id, "name": team.name}

@router.post("/add-member")
def add_member_admin(team_id: int, user_id: int, role: str = "member", admin=Depends(get_current_admin)):
    add_member(team_id, user_id, role)
    return {"ok": True}
