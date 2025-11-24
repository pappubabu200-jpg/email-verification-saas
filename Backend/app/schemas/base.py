from datetime import datetime
from pydantic import BaseModel


class ORMBase(BaseModel):
    id: int
    created_at: datetime | None = None
    updated_at: datetime | None = None

    class Config:
        from_attributes = True
