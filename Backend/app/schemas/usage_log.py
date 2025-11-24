from .base import ORMBase


class UsageLogResponse(ORMBase):
    user_id: int
    api_key_id: int | None
    endpoint: str
    method: str
    status_code: int
    ip: str | None
    user_agent: str | None
