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


# backend/app/api/v1/admin_team.py

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from typing import List, Dict, Any
from backend.app.utils.security import get_current_admin
from backend.app.db import SessionLocal
from backend.app.models.team import Team
from backend.app.models.team_member import TeamMember
from backend.app.models.user import User

router = APIRouter(prefix="/api/v1/admin/team", tags=["admin-team"])

@router.get("/list")
def list_teams(page: int = Query(1, ge=1), per_page: int = Query(50, ge=1, le=200), admin = Depends(get_current_admin)) -> Dict[str, Any]:
    """
    Return paginated list of teams with owner info and member_count.
    """
    db = SessionLocal()
    try:
        q = db.query(Team)
        total = q.count()
        rows = q.order_by(Team.created_at.desc()).limit(per_page).offset((page-1)*per_page).all()

        out = []
        for t in rows:
            # owner info (if present)
            owner = None
            try:
                if t.owner_id:
                    owner_row = db.query(User).get(t.owner_id)
                    owner = {"id": owner_row.id, "email": owner_row.email} if owner_row else None
            except Exception:
                owner = None

            # member count
            member_count = db.query(func.count(TeamMember.id)).filter(TeamMember.team_id == t.id, TeamMember.is_active == True).scalar() or 0

            out.append({
                "id": t.id,
                "name": t.name,
                "slug": t.slug,
                "owner_id": t.owner_id,
                "owner": owner,
                "credits": float(t.credits or 0),
                "is_active": bool(t.is_active),
                "member_count": int(member_count),
                "created_at": str(t.created_at)
            })

        return {"page": page, "per_page": per_page, "total": total, "teams": out}
    finally:
        db.close()



