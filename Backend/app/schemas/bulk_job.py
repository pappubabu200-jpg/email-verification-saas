from .base import ORMBase
from pydantic import BaseModel


class BulkJobResponse(ORMBase):
    user_id: int
    job_id: str
    status: str
    total: int
    processed: int
    valid: int
    invalid: int
    input_path: str | None
    output_path: str | None
    webhook_url: str | None
    team_id: int | None
