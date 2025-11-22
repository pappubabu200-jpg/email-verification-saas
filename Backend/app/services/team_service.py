
# backend/app/services/team_service.py
import logging
from typing import Optional, List
from backend.app.db import SessionLocal
from backend.app.models.team import Team
from backend.app.models.team_member import TeamMember, TEAM_ROLES
from backend.app.models.user import User
from fastapi import HTTPException

logger = logging.getLogger(__name__)

def create_team(owner_id: int, name: str):
    db = SessionLocal()
    try:
        t = Team(owner_id=owner_id, name=name)
        db.add(t)
        db.commit()
        db.refresh(t)
        # create owner as team member
        tm = TeamMember(team_id=t.id, user_id=owner_id, role="owner", invited=False)
        db.add(tm)
        db.commit()
        db.refresh(tm)
        return t
    except Exception as e:
        logger.exception("create_team failed: %s", e)
        raise HTTPException(status_code=500, detail="create_team_failed")
    finally:
        db.close()

def get_team(team_id: int) -> Optional[Team]:
    db = SessionLocal()
    try:
        return db.query(Team).get(team_id)
    finally:
        db.close()

def get_team_by_slug(slug: str) -> Optional[Team]:
    # If you later add slug field this will be useful. For now, search by name fallback.
    db = SessionLocal()
    try:
        return db.query(Team).filter(Team.name == slug).first()
    finally:
        db.close()

def add_member(team_id: int, user_id: int, role: str = "member", invited: bool = False):
    if role not in TEAM_ROLES:
        raise HTTPException(status_code=400, detail="invalid_role")
    db = SessionLocal()
    try:
        team = db.query(Team).get(team_id)
        if not team:
            raise HTTPException(status_code=404, detail="team_not_found")
        # check existing
        existing = db.query(TeamMember).filter(TeamMember.team_id == team_id, TeamMember.user_id == user_id).first()
        if existing:
            # update role if different
            existing.role = role
            existing.invited = invited
            db.add(existing); db.commit(); db.refresh(existing)
            return existing
        tm = TeamMember(team_id=team_id, user_id=user_id, role=role, invited=invited)
        db.add(tm); db.commit(); db.refresh(tm)
        return tm
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("add_member failed: %s", e)
        raise HTTPException(status_code=500, detail="add_member_failed")
    finally:
        db.close()

def remove_member(team_id: int, user_id: int):
    db = SessionLocal()
    try:
        tm = db.query(TeamMember).filter(TeamMember.team_id == team_id, TeamMember.user_id == user_id).first()
        if not tm:
            raise HTTPException(status_code=404, detail="member_not_found")
        # Prevent removing the owner
        if tm.role == "owner":
            raise HTTPException(status_code=403, detail="cannot_remove_owner")
        db.delete(tm); db.commit()
        return True
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("remove_member failed: %s", e)
        raise HTTPException(status_code=500, detail="remove_member_failed")
    finally:
        db.close()

def change_role(team_id: int, user_id: int, new_role: str):
    if new_role not in TEAM_ROLES:
        raise HTTPException(status_code=400, detail="invalid_role")
    db = SessionLocal()
    try:
        tm = db.query(TeamMember).filter(TeamMember.team_id == team_id, TeamMember.user_id == user_id).first()
        if not tm:
            raise HTTPException(status_code=404, detail="member_not_found")
        # Do not allow demoting owner via this function (owner transfer must be explicit)
        if tm.role == "owner" and new_role != "owner":
            raise HTTPException(status_code=403, detail="cannot_demote_owner")
        tm.role = new_role
        db.add(tm); db.commit(); db.refresh(tm)
        return tm
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("change_role failed: %s", e)
        raise HTTPException(status_code=500, detail="change_role_failed")
    finally:
        db.close()

def list_team_members(team_id: int) -> List[TeamMember]:
    db = SessionLocal()
    try:
        return db.query(TeamMember).filter(TeamMember.team_id == team_id).all()
    finally:
        db.close()

def get_user_teams(user_id: int) -> List[Team]:
    db = SessionLocal()
    try:
        rows = db.query(Team).join(TeamMember, Team.id == TeamMember.team_id).filter(TeamMember.user_id == user_id).all()
        return rows
    finally:
        db.close()

def is_user_member_of_team(user_id: int, team_id: int) -> bool:
    db = SessionLocal()
    try:
        tm = db.query(TeamMember).filter(TeamMember.team_id == team_id, TeamMember.user_id == user_id, TeamMember.active == True).first()
        return bool(tm)
    finally:
        db.close()

def get_member_role(user_id: int, team_id: int) -> Optional[str]:
    db = SessionLocal()
    try:
        tm = db.query(TeamMember).filter(TeamMember.team_id == team_id, TeamMember.user_id == user_id).first()
        return tm.role if tm else None
    finally:
        db.close()

def require_role(team_id: int, user_id: int, allowed_roles: List[str]) -> bool:
    role = get_member_role(user_id, team_id)
    if not role:
        return False
    return role in allowed_roles

# backend/app/services/team_service.py
from backend.app.db import SessionLocal
from backend.app.models.team import Team
from backend.app.models.team_member import TeamMember
from backend.app.models.user import User
from fastapi import HTTPException

def is_user_member_of_team(user_id: int, team_id: int) -> bool:
    db = SessionLocal()
    try:
        tm = db.query(TeamMember).filter(TeamMember.team_id==team_id, TeamMember.user_id==user_id, TeamMember.is_active==True).first()
        return bool(tm)
    finally:
        db.close()

def create_team(owner_id: int, name: str, slug: str = None, metadata: str = None) -> Team:
    db = SessionLocal()
    try:
        team = Team(name=name, slug=slug, owner_id=owner_id, metadata=metadata or "", credits=0)
        db.add(team)
        db.commit()
        db.refresh(team)
        # add owner as member with role owner
        member = TeamMember(team_id=team.id, user_id=owner_id, role="owner", is_active=True)
        db.add(member)
        db.commit()
        return team
    finally:
        db.close()

def add_member(team_id: int, user_id: int, role: str = "member") -> TeamMember:
    db = SessionLocal()
    try:
        existing = db.query(TeamMember).filter(TeamMember.team_id==team_id, TeamMember.user_id==user_id).first()
        if existing:
            existing.is_active = True
            existing.role = role
            db.add(existing)
            db.commit()
            db.refresh(existing)
            return existing
        tm = TeamMember(team_id=team_id, user_id=user_id, role=role, is_active=True)
        db.add(tm)
        db.commit()
        db.refresh(tm)
        return tm
    finally:
        db.close()

def remove_member(team_id: int, user_id: int) -> bool:
    db = SessionLocal()
    try:
        tm = db.query(TeamMember).filter(TeamMember.team_id==team_id, TeamMember.user_id==user_id).first()
        if not tm:
            return False
        tm.is_active = False
        db.add(tm); db.commit()
        return True
    finally:
        db.close()



# backend/app/services/team_service.py

from backend.app.db import SessionLocal
from backend.app.models.team import Team
from backend.app.models.team_member import TeamMember
from fastapi import HTTPException
import logging

logger = logging.getLogger(__name__)

def is_user_member_of_team(user_id: int, team_id: int) -> bool:
    db = SessionLocal()
    try:
        q = db.query(TeamMember).filter(
            TeamMember.team_id == team_id,
            TeamMember.user_id == user_id,
            TeamMember.is_active == True
        ).first()
        return q is not None
    finally:
        db.close()

def create_team(owner_id: int, name: str, slug: str = None):
    db = SessionLocal()
    try:
        team = Team(owner_id=owner_id, name=name, slug=slug)
        db.add(team)
        db.commit()
        db.refresh(team)

        member = TeamMember(team_id=team.id, user_id=owner_id, role="owner")
        db.add(member)
        db.commit()

        return team
    finally:
        db.close()

def add_member(team_id: int, user_id: int, role: str = "member"):
    db = SessionLocal()
    try:
        m = TeamMember(team_id=team_id, user_id=user_id, role=role)
        db.add(m)
        db.commit()
        return True
    finally:
        db.close()


from backend.app.db import SessionLocal
from backend.app.models.team_member import TeamMember
from backend.app.models.team import Team
from backend.app.models.user import User
from fastapi import HTTPException

def is_user_member_of_team(user_id: int, team_id: int) -> bool:
    db = SessionLocal()
    try:
        m = db.query(TeamMember).filter(TeamMember.team_id == team_id, TeamMember.user_id == user_id).first()
        return bool(m)
    finally:
        db.close()

def get_team(team_id: int):
    db = SessionLocal()
    try:
        return db.query(Team).get(team_id)
    finally:
        db.close()

def create_team(name: str, owner_id: int):
    db = SessionLocal()
    try:
        t = Team(name=name, owner_id=owner_id, credits=0)
        db.add(t)
        db.commit()
        db.refresh(t)
        # add owner as member
        tm = TeamMember(team_id=t.id, user_id=owner_id, role="owner")
        db.add(tm); db.commit()
        return t
    finally:
        db.close()

def add_member(team_id: int, user_id: int, role: str = "member"):
    db = SessionLocal()
    try:
        if is_user_member_of_team(user_id, team_id):
            return True
        tm = TeamMember(team_id=team_id, user_id=user_id, role=role)
        db.add(tm)
        db.commit()
        return True
    finally:
        db.close()

backend.app.db

