from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field

from ._base import CamelModel


class NodeCreate(CamelModel):
    node_type_id: str
    name: str = Field(..., min_length=1, max_length=100)
    dn: Optional[str] = Field(default=None, max_length=200)
    status: str = Field(default="online", max_length=20)


class NodeUpdate(CamelModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    dn: Optional[str] = Field(default=None, max_length=200)
    status: Optional[str] = Field(default=None, max_length=20)


class NodePositionUpdate(CamelModel):
    x: float
    y: float


class NodeAttrSet(CamelModel):
    field_key: str
    value: Optional[str] = None


class NodeItem(CamelModel):
    id: str
    topology_id: str
    node_type_id: str
    name: str
    dn: Optional[str]
    status: str
    created_at: datetime
    updated_at: datetime


class NodeListItem(NodeItem):
    x: Optional[float] = None
    y: Optional[float] = None


class NodeDetail(NodeItem):
    attrs: dict[str, Any] = {}
    x: Optional[float] = None
    y: Optional[float] = None


class NodeListResponse(CamelModel):
    code: int = 0
    data: dict[str, Any]
    message: str = "ok"
