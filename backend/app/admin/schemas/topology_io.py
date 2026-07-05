"""Topology import/export envelope (M4-02).

Design: `node_type_code` and `edge_type_code` reference the target instance's
existing type config by `code` (UNIQUE), not by id. This keeps export files
portable across instances that share the same type catalog. Original node/edge
ids are preserved in the doc and remapped to fresh ids on import so every
import yields a self-contained, non-colliding topology.
"""
from datetime import datetime
from typing import Any, Optional

from pydantic import Field

from ._base import CamelModel


SCHEMA_VERSION = "1.0"


class TopologyExportNode(CamelModel):
    id: str
    node_type_code: str
    name: str
    dn: Optional[str] = None
    status: str = "online"
    attrs: dict[str, Any] = Field(default_factory=dict)
    canvas: Optional[dict[str, float]] = None  # {"x": ..., "y": ...} or null


class TopologyExportEdge(CamelModel):
    id: str
    edge_type_code: str
    source_id: str
    target_id: str
    status: str = "up"
    attrs: dict[str, Any] = Field(default_factory=dict)


class TopologyExportMeta(CamelModel):
    name: str
    description: Optional[str] = None
    version: int = 1


class TopologyExportDoc(CamelModel):
    schema_version: str = SCHEMA_VERSION
    exported_at: datetime
    topology: TopologyExportMeta
    nodes: list[TopologyExportNode]
    edges: list[TopologyExportEdge]


class TopologyImportResult(CamelModel):
    topology_id: str
    name: str
    node_count: int
    edge_count: int
    canvas_count: int


class TopologyExportResponse(CamelModel):
    code: int = 0
    data: TopologyExportDoc
    message: str = "ok"


class TopologyImportResponse(CamelModel):
    code: int = 0
    data: TopologyImportResult
    message: str = "ok"


class TopologyExcelCounts(CamelModel):
    nodes: int
    edges: int
    groups: int
    node_alarms: int
    group_alarms: int


class TopologyExcelImportResult(CamelModel):
    topology_id: str
    topology_name: str
    counts: TopologyExcelCounts
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class TopologyExcelImportResponse(CamelModel):
    code: int = 0
    data: TopologyExcelImportResult
    message: str = "ok"
