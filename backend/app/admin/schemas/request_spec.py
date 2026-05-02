"""请求契约（M5-01）：headers / query / body 声明 + 鉴权配置。

落地于 `api_configs.config.request` 与 `api_configs.config.auth` 两段子树。
后端 `request_pipeline._step3_5_validate_request` 据此做严格白名单 + 类型校验。

向后兼容约定：
    - `config.request` 缺失 → step 跳过整段校验（M4 老接口零变化）
    - `config.auth` 缺失 / `auth.type == 'none'` → step3 放行
"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import Field, field_validator

from ._base import CamelModel


# ---------- Header ----------
class HeaderSpec(CamelModel):
    """请求头声明。

    - `required=True` 缺失 → 40020
    - `expect_value` 非空且与请求实际值不同 → 40021
    - `expect_value` 为空时仅校验存在性
    - headers **不**做严格白名单（HTTP 标准头会自动注入）
    """

    name: str = Field(..., min_length=1, max_length=100)
    required: bool = False
    expect_value: Optional[str] = Field(default=None, max_length=500)
    example: Optional[str] = Field(default=None, max_length=500)
    description: Optional[str] = Field(default=None, max_length=500)


# ---------- Query ----------
QueryParamType = Literal["string", "int", "bool"]


class QuerySpec(CamelModel):
    """Query 参数声明。

    - `required=True` 缺失 → 40022
    - 类型不匹配（int 解析失败 / bool 不在 {true,false,1,0,yes,no}）→ 40023
    - 严格白名单：未声明的 query key 出现 → 40025
    """

    name: str = Field(..., min_length=1, max_length=100)
    type: QueryParamType = "string"
    required: bool = False
    example: Optional[str] = Field(default=None, max_length=500)
    description: Optional[str] = Field(default=None, max_length=500)


# ---------- Body ----------
BodyContentType = Literal[
    "application/json",
    "application/x-www-form-urlencoded",
    "text/plain",
]


class BodySpec(CamelModel):
    """请求体声明。

    - `required=True` 但请求体空 → 40026
    - `content_type` 仅做声明不做匹配（M5-01 不实现，预留 LEGACY-02 / 错误码 40024）
    - `example` 仅文档展示，本期不做 schema 校验
    """

    content_type: BodyContentType = "application/json"
    required: bool = False
    example: Optional[str] = Field(default=None, max_length=10000)
    description: Optional[str] = Field(default=None, max_length=500)


# ---------- RequestSpec 容器 ----------
class RequestSpec(CamelModel):
    """请求规格容器，对应 `config.request`。

    所有字段缺省 → 等同于"未声明请求规格"，校验 step 直接跳过。
    """

    headers: list[HeaderSpec] = Field(default_factory=list)
    query: list[QuerySpec] = Field(default_factory=list)
    body: Optional[BodySpec] = None

    @field_validator("headers")
    @classmethod
    def _unique_header_names(cls, v: list[HeaderSpec]) -> list[HeaderSpec]:
        seen: set[str] = set()
        for h in v:
            key = h.name.lower()
            if key in seen:
                raise ValueError(f"请求头 {h.name!r} 重复声明")
            seen.add(key)
        return v

    @field_validator("query")
    @classmethod
    def _unique_query_names(cls, v: list[QuerySpec]) -> list[QuerySpec]:
        seen: set[str] = set()
        for q in v:
            if q.name in seen:
                raise ValueError(f"query 参数 {q.name!r} 重复声明")
            seen.add(q.name)
        return v


# ---------- Auth ----------
AuthType = Literal["none", "xtoken", "basic"]


class AuthConfig(CamelModel):
    """鉴权配置，对应 `config.auth`。

    - `type='none'` 或缺省 → step3 放行
    - `type='xtoken'` → 从 `header_name` 指定的 header（默认 `X-Auth-Token`）取值校验 tokens 表
    - `type='basic'` → 从 `Authorization: Basic <b64(user:pwd)>` 解析校验
    """

    type: AuthType = "none"
    header_name: Optional[str] = Field(default=None, max_length=100)


__all__ = [
    "HeaderSpec",
    "QuerySpec",
    "QueryParamType",
    "BodySpec",
    "BodyContentType",
    "RequestSpec",
    "AuthConfig",
    "AuthType",
]
