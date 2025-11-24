from .base import ORMBase
from pydantic import BaseModel


class FailedJobResponse(ORMBase):
    job_type: str
    job_id: int | None
    attempts: int
    error_message: str
