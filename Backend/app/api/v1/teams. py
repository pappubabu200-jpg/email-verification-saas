# backend/app/api/v1/teams.py
from fastapi import APIRouter, Depends, HTTPException
from backend.app.db import SessionLocal
from backend.app.models.team import Team
from backend.app.models.team_member import TeamMember
from backend.app.utils.security import get_current_user, get_current_admin
import uuid

router = APIRouter(prefix="/api/v1/teams", tags=["teams"])

@router.post("/create")
def create_team(name: str, current_user = Depends(get_current_user)):
    db = SessionLocal()
    try:
        slug = name.lower().replace(" ", "-") + "-" + uuid.uuid4().hex[:6]
        t = Team(owner_id=current_user.id, name=name, slug=slug)
        db.add(t); db.commit(); db.refresh(t)
        # add owner as team member
        tm = TeamMember(team_id=t.id, user_id=current_user.id, role="owner")
        db.add(tm); db.commit()
        return {"team": {"id": t.id, "name": t.name, "slug": t.slug}}
    finally:
        db.close()

@router.post("/{team_id}/add-member")
def add_member(team_id: int, user_id: int, role: str = "member", current_user = Depends(get_current_user)):
    db = SessionLocal()
    try:
        team = db.query(Team).get(team_id)
        if not team:
            raise HTTPException(status_code=404, detail="team_not_found")
        if team.owner_id != current_user.id:
            raise HTTPException(status_code=403, detail="owner_required")
        tm = TeamMember(team_id=team_id, user_id=user_id, role=role)
        db.add(tm); db.commit()
        return {"ok": True}
    finally:
        db.close()
