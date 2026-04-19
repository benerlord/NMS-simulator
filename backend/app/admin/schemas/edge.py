from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field

from ._base import CamelModel


class EdgeCreate(CamelModel):
    edge_type_id: str
    source_id: str
    target_id: str
    status: str = Field(default="up", max_length=20)


class EdgeUpdate(CamelModel):
    status: Optional[str] = Field(default=None, max_length=20)


class EdgeAttrSet(CamelModel):
    field_key: str
    value: Optional[str] = None


class EdgeItem(CamelModel):
    id: str
    topology_id: str
    edge_type_id: str
    source_id: str
    target_id: str
    status: str
    created_at: datetime
    updated_at: datetime


class EdgeDetail(EdgeItem):
    attrs: dict[str, Any] = {}


class EdgeListResponse(CamelModel):
    code: int = 0
    data: dict[str, Any]
    message: str = "ok"
