from .base import ORMBase


class TeamCreditTransactionResponse(ORMBase):
    team_id: int
    amount: float
    balance_after: float
    type: str
    reference: str | None
    metadata: str | None
