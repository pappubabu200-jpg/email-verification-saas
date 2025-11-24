from pydantic import BaseModel
from .base import ORMBase


class TeamMemberBase(BaseModel):
    role: str
    active: bool = True


class TeamMemberResponse(ORMBase, TeamMemberBase):
    user_id: int
    team_id: int
