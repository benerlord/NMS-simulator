from typing import Optional

from pydantic import Field

from ._base import CamelModel


class DomainCreate(CamelModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = Field(default=None, max_length=500)


class DomainUpdate(CamelModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    description: Optional[str] = Field(default=None, max_length=500)


class DomainItem(CamelModel):
    id: str
    name: str
    description: Optional[str]
    topology_count: int = 0
    created_at: str
    updated_at: str
