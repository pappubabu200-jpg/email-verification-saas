from .base import ORMBase


class ExtractorJobResponse(ORMBase):
    user_id: int
    job_id: str
    status: str
    input_path: str | None
    output_path: str | None
    total: int
    processed: int
    error_message: str | None
    team_id: int | None
