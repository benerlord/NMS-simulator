from typing import Optional

from pydantic import Field

from ._base import CamelModel


class MockInstanceCreate(CamelModel):
    name: str = Field(..., min_length=1, max_length=100)
    topology_id: str = Field(..., min_length=1)
    port: int = Field(..., ge=1, le=65535)
    description: Optional[str] = Field(default=None, max_length=200)
    enabled: bool = True


class MockInstanceUpdate(CamelModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    topology_id: Optional[str] = None
    port: Optional[int] = Field(default=None, ge=1, le=65535)
    description: Optional[str] = Field(default=None, max_length=200)
    enabled: Optional[bool] = None


class MockInstanceItem(CamelModel):
    id: str
    name: str
    topology_id: str
    topology_name: str
    port: int
    description: Optional[str]
    enabled: bool
    api_count: int = 0
    created_at: str
    updated_at: str


class RequestLogItem(CamelModel):
    id: int
    ts: str
    api_id: Optional[str] = None
    method: str
    path: str
    query: Optional[str] = None
    status_code: int
    duration_ms: int
    client_ip: Optional[str] = None
    error_message: Optional[str] = None
    instance_id: Optional[str] = None
