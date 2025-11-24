from .base import ORMBase


class DecisionMakerResponse(ORMBase):
    user_id: int | None
    company: str | None
    domain: str | None
    first_name: str | None
    last_name: str | None
    title: str | None
    role: str | None
    email: str | None
    source: str | None
    raw: str | None
    verified: bool
