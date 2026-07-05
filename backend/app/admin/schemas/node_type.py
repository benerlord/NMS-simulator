from datetime import datetime
from typing import Any, Optional, List

from pydantic import BaseModel, Field, model_validator

from ._base import CamelModel


# --- field input (整批同步用) ---

class NodeTypeFieldInput(CamelModel):
    """整批同步用 — 无 id；field_key 是稳定主键。

    注意：sort_order 由数组顺序决定，客户端传入的 sort_order 值会被服务端忽略并重写。
    """
    field_key: str = Field(..., min_length=1, max_length=50)
    field_label: str = Field(..., min_length=1, max_length=100)
    field_type: str = Field(..., pattern="^(text|number|select|boolean|array)$")
    max_length: Optional[int] = Field(default=None, ge=1)
    default_value: Optional[str] = Field(default=None, max_length=200)
    options: Optional[str] = Field(default=None, max_length=500)
    required: bool = Field(default=False)
    sort_order: int = Field(default=0)

    @model_validator(mode='after')
    def validate_max_length_for_text(self) -> 'NodeTypeFieldInput':
        if self.field_type != 'text':
            return self
        if self.max_length is None:
            object.__setattr__(self, 'max_length', 255)
        return self

    @model_validator(mode='after')
    def validate_array_default(self) -> 'NodeTypeFieldInput':
        if self.field_type != 'array' or not self.default_value:
            return self
        import json
        try:
            v = json.loads(self.default_value)
        except json.JSONDecodeError:
            raise ValueError('array 类型的 default_value 必须是合法 JSON')
        if not isinstance(v, list):
            raise ValueError('array 类型的 default_value 必须是 JSON array')
        return self


# --- node_types ---

class NodeTypeCreate(CamelModel):
    code: str = Field(..., min_length=1, max_length=50)
    name: str = Field(..., min_length=1, max_length=100)
    category: str = Field(..., min_length=1, max_length=50)
    description: Optional[str] = Field(default=None, max_length=500)
    domain_ids: Optional[list[str]] = Field(default=None)
    fields: Optional[list[NodeTypeFieldInput]] = Field(default=None)


class NodeTypeUpdate(CamelModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    description: Optional[str] = Field(default=None, max_length=500)
    domain_ids: Optional[list[str]] = Field(default=None)
    fields: Optional[list[NodeTypeFieldInput]] = Field(default=None)


class NodeTypeFieldItem(CamelModel):
    id: int
    node_type_id: str
    field_key: str
    field_label: str
    field_type: str
    max_length: Optional[int]
    default_value: Optional[str]
    options: Optional[str]
    required: bool
    sort_order: int


class NodeTypeItem(CamelModel):
    id: str
    code: str
    name: str
    category: str
    description: Optional[str]
    domain_ids: list[str] = []
    domain_names: list[str] = []
    created_at: datetime
    updated_at: datetime


class NodeTypeDetail(NodeTypeItem):
    fields: list[NodeTypeFieldItem] = []


class NodeTypeBatchDelete(BaseModel):
    ids: list[str] = Field(..., min_length=1, max_length=200)


class EdgeTypeBatchDelete(BaseModel):
    ids: list[str] = Field(..., min_length=1, max_length=200)


class TypeExportRequest(CamelModel):
    ids: Optional[list[str]] = Field(default=None)


class TypeImportResult(CamelModel):
    created: int = 0
    updated: int = 0
    total_fields: int = 0
    errors: list[str] = []


class TypeImportPreviewItem(CamelModel):
    code: str
    name: str
    old_name: Optional[str] = None


class TypeImportPreview(CamelModel):
    to_create: list[TypeImportPreviewItem] = []
    to_update: list[TypeImportPreviewItem] = []
    errors: list[str] = []


class NodeTypeDomainsUpdate(CamelModel):
    domain_ids: list[str] = []  # 空数组 = 解除所有域关联


class NodeTypeBatchDomainsUpdate(CamelModel):
    node_type_ids: list[str] = Field(..., min_length=1)
    domain_ids: list[str] = []  # 空数组 = 解除所有域关联


# --- edge field input (整批同步用) ---

class EdgeTypeFieldInput(CamelModel):
    """整批同步用 — 无 id；field_key 是稳定主键。"""
    field_key: str = Field(..., min_length=1, max_length=50)
    field_label: str = Field(..., min_length=1, max_length=100)
    field_type: str = Field(..., pattern="^(text|number|select|boolean|array)$")
    max_length: Optional[int] = Field(default=None, ge=1)
    default_value: Optional[str] = Field(default=None, max_length=200)
    options: Optional[str] = Field(default=None, max_length=500)
    required: bool = Field(default=False)
    sort_order: int = Field(default=0)

    @model_validator(mode='after')
    def validate_max_length_for_text(self) -> 'EdgeTypeFieldInput':
        if self.field_type != 'text':
            return self
        if self.max_length is None:
            object.__setattr__(self, 'max_length', 255)
        return self

    @model_validator(mode='after')
    def validate_array_default(self) -> 'EdgeTypeFieldInput':
        if self.field_type != 'array' or not self.default_value:
            return self
        import json
        try:
            v = json.loads(self.default_value)
        except json.JSONDecodeError:
            raise ValueError('array 类型的 default_value 必须是合法 JSON')
        if not isinstance(v, list):
            raise ValueError('array 类型的 default_value 必须是 JSON array')
        return self


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
    fields: Optional[list[EdgeTypeFieldInput]] = Field(default=None)


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
    fields: Optional[list[EdgeTypeFieldInput]] = Field(default=None)


class EdgeTypeFieldItem(CamelModel):
    id: int
    edge_type_id: str
    field_key: str
    field_label: str
    field_type: str
    max_length: Optional[int]
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


# --- delete-impact (共用) ---

class FieldDeleteImpactRequest(CamelModel):
    field_keys: list[str] = Field(..., min_length=1, max_length=200)


class FieldDeleteImpactItem(CamelModel):
    field_key: str
    affected_node_count: int = 0


class FieldDeleteImpactResponse(CamelModel):
    items: list[FieldDeleteImpactItem]


# --- edge_type Excel I/O ---

class EdgeTypeImportPreviewItem(CamelModel):
    code: str
    name: str
    old_name: Optional[str] = None


class EdgeTypeImportPreview(CamelModel):
    to_create: list[EdgeTypeImportPreviewItem] = Field(default_factory=list)
    to_update: list[EdgeTypeImportPreviewItem] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


class EdgeTypeImportResult(CamelModel):
    created: int = 0
    updated: int = 0
    total_fields: int = 0
    errors: list[str] = Field(default_factory=list)
