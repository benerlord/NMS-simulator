from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field

from ._base import CamelModel


class TokenCreate(CamelModel):
    token: str = Field(..., min_length=1, max_length=500)
    expires_at: datetime
    auth_type: str = Field(default="xtoken", max_length=20)
    issued_by_api: Optional[str] = Field(default=None, max_length=500)
    meta: dict[str, Any] = Field(default_factory=dict)


class TokenRevoke(CamelModel):
    ...


class TokenItem(CamelModel):
    token: str
    issued_at: datetime
    expires_at: datetime
    revoked: bool
    issued_by_api: Optional[str]
    meta: dict[str, Any] = Field(default_factory=dict)


class TokenListData(CamelModel):
    items: list[TokenItem]
    total: int
    page: int
    pageSize: int


class TokenListResponse(CamelModel):
    code: int = 0
    data: TokenListData
    message: str = "ok"


class TokenItemResponse(CamelModel):
    code: int = 0
    data: TokenItem
    message: str = "ok"
