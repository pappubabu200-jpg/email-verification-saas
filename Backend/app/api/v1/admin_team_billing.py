# backend/app/api/v1/admin_team_billing.py
from fastapi import APIRouter, Depends, HTTPException, Body
from backend.app.utils.security import get_current_admin
from backend.app.db import SessionLocal
from backend.app.models.team import Team
from backend.app.services.team_billing_service import add_team_credits, get_team_balance
from pydantic import BaseModel
from decimal import Decimal

router = APIRouter(prefix="/api/v1/admin/team-billing", tags=["admin-team-billing"])

class TopUpIn(BaseModel):
    team_id: int
    amount: float
    reference: str = None

@router.get("/teams")
def list_teams(admin = Depends(get_current_admin)):
    db = SessionLocal()
    try:
        rows = db.query(Team).order_by(Team.created_at.desc()).all()
        return [{"id": r.id, "name": r.name, "owner_id": r.owner_id, "credits": float(r.credits or 0)} for r in rows]
    finally:
        db.close()

@router.post("/topup")
def topup(payload: TopUpIn, admin = Depends(get_current_admin)):
    try:
        res = add_team_credits(payload.team_id, Decimal(str(payload.amount)), reference=payload.reference)
        return {"ok": True, "result": res}
    except HTTPException as e:
        raise e
