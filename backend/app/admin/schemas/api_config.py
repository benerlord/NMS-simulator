from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator

from ._base import CamelModel


ALLOWED_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE"}
ALLOWED_DATA_SOURCES = {"sql", "static"}


class ApiConfigCreate(CamelModel):
    name: str = Field(..., min_length=1, max_length=100)
    method: str = Field(..., min_length=1, max_length=10)
    path: str = Field(..., min_length=1, max_length=500)
    enabled: bool = True
    group_name: Optional[str] = Field(default=None, max_length=100)
    data_source: str = Field(..., min_length=1, max_length=20)
    topology_id: Optional[str] = None
    sql_text: Optional[str] = None
    config: dict[str, Any] = Field(default_factory=dict)

    @field_validator("method")
    @classmethod
    def _upper_method(cls, v: str) -> str:
        v = v.upper()
        if v not in ALLOWED_METHODS:
            raise ValueError(f"method 必须为 {sorted(ALLOWED_METHODS)} 之一")
        return v

    @field_validator("data_source")
    @classmethod
    def _check_source(cls, v: str) -> str:
        if v not in ALLOWED_DATA_SOURCES:
            raise ValueError(f"data_source 必须为 {sorted(ALLOWED_DATA_SOURCES)} 之一")
        return v


class ApiConfigUpdate(CamelModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    method: Optional[str] = Field(default=None, max_length=10)
    path: Optional[str] = Field(default=None, max_length=500)
    group_name: Optional[str] = Field(default=None, max_length=100)
    data_source: Optional[str] = Field(default=None, max_length=20)
    sql_text: Optional[str] = None
    config: Optional[dict[str, Any]] = None

    @field_validator("method")
    @classmethod
    def _upper_method(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        v = v.upper()
        if v not in ALLOWED_METHODS:
            raise ValueError(f"method 必须为 {sorted(ALLOWED_METHODS)} 之一")
        return v

    @field_validator("data_source")
    @classmethod
    def _check_source(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in ALLOWED_DATA_SOURCES:
            raise ValueError(f"data_source 必须为 {sorted(ALLOWED_DATA_SOURCES)} 之一")
        return v


class ApiConfigEnabledPatch(CamelModel):
    enabled: bool


class ApiConfigTopologyPatch(CamelModel):
    topology_id: Optional[str] = None


class ApiConfigItem(CamelModel):
    id: str
    name: str
    method: str
    path: str
    enabled: bool
    group_name: Optional[str]
    data_source: str
    topology_id: Optional[str]
    created_at: datetime
    updated_at: datetime


class ApiConfigDetail(ApiConfigItem):
    sql_text: Optional[str] = None
    config: dict[str, Any] = Field(default_factory=dict)


class ApiConfigListResponse(CamelModel):
    code: int = 0
    data: dict[str, Any]
    message: str = "ok"


class ApiConfigDetailResponse(CamelModel):
    code: int = 0
    data: ApiConfigDetail
    message: str = "ok"


class ApiTestRequest(CamelModel):
    headers: dict[str, Any] = Field(default_factory=dict)
    query: dict[str, Any] = Field(default_factory=dict)
    body: Optional[Any] = None


class ApiTestResult(CamelModel):
    status_code: int
    headers: dict[str, Any] = Field(default_factory=dict)
    body: Any = None
    duration_ms: int = 0
    generated_sql: Optional[str] = None
    bound_params: dict[str, Any] = Field(default_factory=dict)


class ApiTestResponse(CamelModel):
    code: int = 0
    data: ApiTestResult
    message: str = "ok"
