from .base import ORMBase


class WebhookEventResponse(ORMBase):
    endpoint_id: int
    provider: str | None
    event_type: str
    payload: str | None
    delivered: bool
    retry_count: int
    response_status: int | None
    response_body: str | None
    delivered_at: str | None
    failed_at: str | None
