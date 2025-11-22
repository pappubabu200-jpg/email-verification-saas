# backend/app/services/team_context.py
from backend.app.db import SessionLocal
from backend.app.models.team_member import TeamMember
from fastapi import HTTPException


def get_user_team(user_id: int):
    """
    Returns (team, role) for user.
    If no team exists → user works in default personal team.
    """
    db = SessionLocal()
    try:
        tm = db.query(TeamMember).filter(TeamMember.user_id == user_id).first()
        if not tm:
            # User has no team → auto create personal team
            from backend.app.models.team import Team
            team = Team(name=f"user-{user_id}-team", owner_id=user_id)
            db.add(team)
            db.commit()
            db.refresh(team)

            # make user owner
            tm = TeamMember(team_id=team.id, user_id=user_id, role="owner")
            db.add(tm)
            db.commit()
            db.refresh(tm)

        return tm.team_id, tm.role
    finally:
        db.close()



