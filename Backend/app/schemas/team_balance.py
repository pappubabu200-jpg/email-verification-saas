from .base import ORMBase


class TeamBalanceResponse(ORMBase):
    team_id: int
    balance: float
