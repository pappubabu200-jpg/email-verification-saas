
from pydantic import BaseModel
from datetime import datetime
from .base import ORMBase


class AuditLogResponse(ORMBase):
    user_id: int | None
    team_id: int | None
    event_type: str
    message: str
    ip_address: str | None
    request_id: str | None
    meta: dict | None
