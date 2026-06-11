from datetime import datetime
from typing import Optional

from pydantic import Field, model_validator

from ._base import CamelModel


# --- alarm_schema fields ---

class AlarmSchemaFieldCreate(CamelModel):
    field_key: str = Field(..., min_length=1, max_length=50)
    field_label: str = Field(..., min_length=1, max_length=100)
    field_type: str = Field(..., pattern="^(text|number|select|boolean)$")
    max_length: Optional[int] = Field(default=None, ge=1)
    default_value: Optional[str] = Field(default=None, max_length=200)
    options: Optional[str] = Field(default=None, max_length=500)
    required: bool = Field(default=False)
    sort_order: int = Field(default=0)

    @model_validator(mode='after')
    def validate_max_length_for_text(self) -> 'AlarmSchemaFieldCreate':
        if self.field_type != 'text':
            return self
        if self.max_length is None or self.max_length < 1:
            raise ValueError('文本类型必须设置 max_length >= 1')
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


# --- alarm_schemas ---

class AlarmSchemaCreate(CamelModel):
    code: str = Field(..., min_length=1, max_length=50)
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = Field(default=None, max_length=500)
    fields: list[AlarmSchemaFieldCreate] = Field(default_factory=list)


class AlarmSchemaUpdate(CamelModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    description: Optional[str] = Field(default=None, max_length=500)
    fields: Optional[list[AlarmSchemaFieldCreate]] = Field(default=None)


class AlarmSchemaItem(CamelModel):
    id: str
    code: str
    name: str
    description: Optional[str]
    created_at: datetime
    updated_at: datetime


class AlarmSchemaDetail(AlarmSchemaItem):
    fields: list[AlarmSchemaFieldItem] = []


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
    attrs: dict[str, Optional[str]] = {}
    created_at: datetime
    updated_at: datetime
