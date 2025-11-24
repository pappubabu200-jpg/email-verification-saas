from .base import ORMBase


class SuppressionResponse(ORMBase):
    user_id: int | None
    email: str
    reason: str | None
