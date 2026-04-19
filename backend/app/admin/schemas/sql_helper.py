from typing import Any

from pydantic import Field

from ._base import CamelModel


class SqlViewItem(CamelModel):
    name: str
    columns: list[str]
    sql: str


class SqlViewsData(CamelModel):
    node_views: list[SqlViewItem]
    edge_views: list[SqlViewItem]
    generic: list[SqlViewItem]


class SqlViewsResponse(CamelModel):
    code: int = 0
    data: SqlViewsData
    message: str = "ok"


class SqlPreviewRequest(CamelModel):
    topology_id: str
    sql: str
    params: dict[str, Any] = Field(default_factory=dict)
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=50, ge=1, le=1000)


class SqlExecuteRequest(SqlPreviewRequest):
    pass
