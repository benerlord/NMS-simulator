from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field

from ._base import CamelModel


# --- node_types ---

class NodeTypeCreate(CamelModel):
    code: str = Field(..., min_length=1, max_length=50)
    name: str = Field(..., min_length=1, max_length=100)
    category: str = Field(..., min_length=1, max_length=50)
    icon: Optional[str] = Field(default=None, max_length=50)
    color: Optional[str] = Field(default=None, max_length=20)
    shape: Optional[str] = Field(default=None, max_length=20)
    render_mode: str = Field(default="none", pattern="^(none|flat)$")
    dn_template: Optional[str] = Field(default=None, max_length=200)
    description: Optional[str] = Field(default=None, max_length=500)


class NodeTypeUpdate(CamelModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    icon: Optional[str] = Field(default=None, max_length=50)
    color: Optional[str] = Field(default=None, max_length=20)
    shape: Optional[str] = Field(default=None, max_length=20)
    render_mode: Optional[str] = Field(default=None, pattern="^(none|flat)$")
    dn_template: Optional[str] = Field(default=None, max_length=200)
    description: Optional[str] = Field(default=None, max_length=500)


class NodeTypeFieldCreate(CamelModel):
    field_key: str = Field(..., min_length=1, max_length=50)
    field_label: str = Field(..., min_length=1, max_length=100)
    field_type: str = Field(..., pattern="^(text|number|select|boolean)$")
    default_value: Optional[str] = Field(default=None, max_length=200)
    options: Optional[str] = Field(default=None, max_length=500)
    required: bool = Field(default=False)
    sort_order: int = Field(default=0)


class NodeTypeFieldUpdate(CamelModel):
    field_label: Optional[str] = Field(default=None, min_length=1, max_length=100)
    field_type: Optional[str] = Field(default=None, pattern="^(text|number|select|boolean)$")
    default_value: Optional[str] = Field(default=None, max_length=200)
    options: Optional[str] = Field(default=None, max_length=500)
    required: Optional[bool] = Field(default=None)
    sort_order: Optional[int] = Field(default=None)


class NodeTypeFieldItem(CamelModel):
    id: int
    node_type_id: str
    field_key: str
    field_label: str
    field_type: str
    default_value: Optional[str]
    options: Optional[str]
    required: bool
    sort_order: int


class NodeTypeItem(CamelModel):
    id: str
    code: str
    name: str
    category: str
    icon: Optional[str]
    color: Optional[str]
    shape: Optional[str]
    render_mode: str
    dn_template: Optional[str]
    description: Optional[str]
    created_at: datetime
    updated_at: datetime


class NodeTypeDetail(NodeTypeItem):
    fields: list[NodeTypeFieldItem] = []


# --- edge_types ---

class EdgeTypeCreate(CamelModel):
    code: str = Field(..., min_length=1, max_length=50)
    name: str = Field(..., min_length=1, max_length=100)
    semantic: str = Field(default="connect", pattern="^(connect|contain)$")
    directed: bool = Field(default=True)
    exclusive_target: bool = Field(default=False)
    allow_source_type_codes: Optional[str] = Field(default=None, max_length=500)
    allow_target_type_codes: Optional[str] = Field(default=None, max_length=500)
    line_style: Optional[str] = Field(default=None, max_length=20)
    color: Optional[str] = Field(default=None, max_length=20)
    description: Optional[str] = Field(default=None, max_length=500)


class EdgeTypeUpdate(CamelModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    semantic: Optional[str] = Field(default=None, pattern="^(connect|contain)$")
    directed: Optional[bool] = Field(default=None)
    exclusive_target: Optional[bool] = Field(default=None)
    allow_source_type_codes: Optional[str] = Field(default=None, max_length=500)
    allow_target_type_codes: Optional[str] = Field(default=None, max_length=500)
    line_style: Optional[str] = Field(default=None, max_length=20)
    color: Optional[str] = Field(default=None, max_length=20)
    description: Optional[str] = Field(default=None, max_length=500)


class EdgeTypeFieldCreate(CamelModel):
    field_key: str = Field(..., min_length=1, max_length=50)
    field_label: str = Field(..., min_length=1, max_length=100)
    field_type: str = Field(..., pattern="^(text|number|select|boolean)$")
    default_value: Optional[str] = Field(default=None, max_length=200)
    options: Optional[str] = Field(default=None, max_length=500)
    required: bool = Field(default=False)
    sort_order: int = Field(default=0)


class EdgeTypeFieldUpdate(CamelModel):
    field_label: Optional[str] = Field(default=None, min_length=1, max_length=100)
    field_type: Optional[str] = Field(default=None, pattern="^(text|number|select|boolean)$")
    default_value: Optional[str] = Field(default=None, max_length=200)
    options: Optional[str] = Field(default=None, max_length=500)
    required: Optional[bool] = Field(default=None)
    sort_order: Optional[int] = Field(default=None)


class EdgeTypeFieldItem(CamelModel):
    id: int
    edge_type_id: str
    field_key: str
    field_label: str
    field_type: str
    default_value: Optional[str]
    options: Optional[str]
    required: bool
    sort_order: int


class EdgeTypeItem(CamelModel):
    id: str
    code: str
    name: str
    semantic: str
    directed: bool
    exclusive_target: bool
    allow_source_type_codes: Optional[str]
    allow_target_type_codes: Optional[str]
    line_style: Optional[str]
    color: Optional[str]
    description: Optional[str]
    created_at: datetime
    updated_at: datetime


class EdgeTypeDetail(EdgeTypeItem):
    fields: list[EdgeTypeFieldItem] = []
