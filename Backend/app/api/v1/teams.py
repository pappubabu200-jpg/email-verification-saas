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

# backend/app/api/v1/teams.py
from fastapi import APIRouter, Depends, HTTPException, Path, Query
from pydantic import BaseModel
from typing import Optional
from backend.app.utils.security import get_current_user
from backend.app.services.team_service import (
    create_team, add_member, remove_member, change_role,
    list_team_members, get_user_teams, get_team
)
from backend.app.db import SessionLocal

router = APIRouter(prefix="/api/v1/teams", tags=["teams"])

class CreateTeamIn(BaseModel):
    name: str

class AddMemberIn(BaseModel):
    user_id: int
    role: Optional[str] = "member"
    invited: Optional[bool] = False

class ChangeRoleIn(BaseModel):
    user_id: int
    new_role: str

@router.post("/create")
def api_create_team(payload: CreateTeamIn, current_user = Depends(get_current_user)):
    team = create_team(current_user.id, payload.name)
    return {"ok": True, "team": {"id": team.id, "name": team.name}}

@router.post("/{team_id}/add-member")
def api_add_member(team_id: int = Path(...), payload: AddMemberIn = None, current_user = Depends(get_current_user)):
    # Only team owner or admins can add members — simple check
    t = get_team(team_id)
    if not t:
        raise HTTPException(status_code=404, detail="team_not_found")
    # owner only check: load team members and ensure current_user is owner/admin
    members = list_team_members(team_id)
    # find current user's role
    my_role = None
    for m in members:
        if m.user_id == current_user.id:
            my_role = m.role
            break
    if my_role not in ("owner", "admin"):
        raise HTTPException(status_code=403, detail="only_owner_or_admin_can_add")
    tm = add_member(team_id, payload.user_id, payload.role, payload.invited)
    return {"ok": True, "member": {"id": tm.id, "user_id": tm.user_id, "role": tm.role}}

@router.post("/{team_id}/remove-member")
def api_remove_member(team_id: int = Path(...), user_id: int = Query(...), current_user = Depends(get_current_user)):
    # Only owner or admin can remove (owner cannot be removed)
    members = list_team_members(team_id)
    my_role = None
    for m in members:
        if m.user_id == current_user.id:
            my_role = m.role
            break
    if my_role not in ("owner", "admin"):
        raise HTTPException(status_code=403, detail="only_owner_or_admin_can_remove")
    remove_member(team_id, user_id)
    return {"ok": True}

@router.post("/{team_id}/change-role")
def api_change_role(team_id: int = Path(...), payload: ChangeRoleIn = None, current_user = Depends(get_current_user)):
    # Only owner can change roles (for simplicity)
    members = list_team_members(team_id)
    my_role = None
    for m in members:
        if m.user_id == current_user.id:
            my_role = m.role
            break
    if my_role != "owner":
        raise HTTPException(status_code=403, detail="only_owner_can_change_role")
    tm = change_role(team_id, payload.user_id, payload.new_role)
    return {"ok": True, "member": {"id": tm.id, "user_id": tm.user_id, "role": tm.role}}

@router.get("/my-teams")
def api_my_teams(current_user = Depends(get_current_user)):
    rows = get_user_teams(current_user.id)
    return {"teams": [{"id": r.id, "name": r.name} for r in rows]}

@router.get("/{team_id}/members")
def api_list_members(team_id: int, current_user = Depends(get_current_user)):
    members = list_team_members(team_id)
    return {"members": [{"id": m.id, "user_id": m.user_id, "role": m.role, "invited": m.invited} for m in members]}
