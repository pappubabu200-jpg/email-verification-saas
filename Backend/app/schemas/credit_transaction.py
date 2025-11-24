from .base import ORMBase


class CreditTransactionResponse(ORMBase):
    user_id: int | None
    team_id: int | None
    amount: float
    balance_after: float
    type: str
    reference: str | None
    metadata: str | None
