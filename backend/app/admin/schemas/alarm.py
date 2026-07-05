from datetime import datetime
from typing import Optional

from pydantic import Field, model_validator, field_validator

from ._base import CamelModel


# --- alarm_schema fields ---

class AlarmSchemaFieldCreate(CamelModel):
    field_key: str = Field(..., min_length=1, max_length=50)
    field_label: str = Field(..., min_length=1, max_length=100)
    field_type: str = Field(..., pattern="^(text|number|select|boolean|array)$")
    max_length: Optional[int] = Field(default=None, ge=1)
    default_value: Optional[str] = Field(default=None, max_length=200)
    options: Optional[str] = Field(default=None, max_length=500)
    required: bool = Field(default=False)
    sort_order: int = Field(default=0)
    mapping_target: Optional[str] = Field(default=None, max_length=50)

    @field_validator('mapping_target')
    @classmethod
    def validate_mapping_target(cls, v: Optional[str]) -> Optional[str]:
        if v is None or v == '':
            return None
        import re
        if not re.match(r'^[A-Za-z_][A-Za-z0-9_]*$', v):
            raise ValueError('mapping_target 必须是合法标识符（字母/数字/下划线，以字母或下划线开头）')
        return v

    @model_validator(mode='after')
    def validate_max_length_for_text(self) -> 'AlarmSchemaFieldCreate':
        if self.field_type != 'text':
            return self
        if self.max_length is None:
            object.__setattr__(self, 'max_length', 255)
        return self

    @model_validator(mode='after')
    def validate_array_default(self) -> 'AlarmSchemaFieldCreate':
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


class AlarmSchemaFieldItem(CamelModel):
    id: int
    alarm_schema_id: str
    field_key: str
    field_label: str
    field_type: str
    max_length: Optional[int]
    default_value: Optional[str]
    options: Optional[str]
    required: bool
    sort_order: int
    mapping_target: Optional[str] = None


# --- alarm_schemas ---

class AlarmSchemaCreate(CamelModel):
    code: str = Field(..., min_length=1, max_length=50)
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = Field(default=None, max_length=500)
    display_field_key: Optional[str] = Field(default=None, max_length=50)
    fields: list[AlarmSchemaFieldCreate] = Field(default_factory=list)


class AlarmSchemaUpdate(CamelModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    description: Optional[str] = Field(default=None, max_length=500)
    display_field_key: Optional[str] = Field(default=None, max_length=50)
    fields: Optional[list[AlarmSchemaFieldCreate]] = Field(default=None)


class AlarmSchemaItem(CamelModel):
    id: str
    code: str
    name: str
    description: Optional[str]
    display_field_key: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class AlarmSchemaDetail(AlarmSchemaItem):
    fields: list[AlarmSchemaFieldItem] = Field(default_factory=list)


# --- topology binding ---

class TopologyAlarmSchemaPatch(CamelModel):
    alarm_schema_id: Optional[str] = None  # None / "" = 解绑
    clear_existing: bool = False


# --- node alarms ---

class NodeAlarmAttrSet(CamelModel):
    attrs: dict[str, Optional[str]]


class NodeAlarmCreate(CamelModel):
    attrs: Optional[dict[str, Optional[str]]] = None  # 未传 = 用 default_value 填充


class NodeAlarmItem(CamelModel):
    id: str
    node_id: str
    alarm_index: int
    attrs: dict[str, Optional[str]] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


# --- node group alarms ---

class NodeGroupAlarmAttrSet(CamelModel):
    attrs: dict[str, Optional[str]]


class NodeGroupAlarmCreate(CamelModel):
    attrs: Optional[dict[str, Optional[str]]] = None  # 未传 = 用 default_value 填


class NodeGroupAlarmItem(CamelModel):
    id: str
    node_group_id: str
    alarm_index: int
    attrs: dict[str, Optional[str]] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


# --- alarm_schema Excel I/O ---

class AlarmSchemaExportRequest(CamelModel):
    ids: Optional[list[str]] = Field(default=None)


class AlarmSchemaImportPreviewItem(CamelModel):
    code: str
    name: str
    old_name: Optional[str] = None


class AlarmSchemaImportPreview(CamelModel):
    to_create: list[AlarmSchemaImportPreviewItem] = Field(default_factory=list)
    to_update: list[AlarmSchemaImportPreviewItem] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


class AlarmSchemaImportResult(CamelModel):
    created: int = 0
    updated: int = 0
    total_fields: int = 0
    errors: list[str] = Field(default_factory=list)
