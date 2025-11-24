from .base import ORMBase
from pydantic import BaseModel


class DomainCacheResponse(ORMBase):
    domain: str
    has_dns: bool
    mx_found: bool
    is_disposable: bool
    is_catch_all: bool
    provider: str | None
