from .base import ORMBase


class WebhookEndpointResponse(ORMBase):
    user_id: int | None
    team_id: int | None
    url: str
    description: str | None
    secret: str
    events: str
    active: bool
    api_version: str | None
    last_success_at: str | None
    last_failure_at: str | None
    last_status_code: int | None
