from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field

from ._base import CamelModel


class TopologyCreate(CamelModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = Field(default=None, max_length=500)
    domain_id: Optional[str] = Field(default=None)


class TopologyUpdate(CamelModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    description: Optional[str] = Field(default=None, max_length=500)
    domain_id: Optional[str] = Field(default=None)


class TopologyStats(CamelModel):
    node_count: int = 0
    edge_count: int = 0


class TopologyListItem(CamelModel):
    id: str
    name: str
    description: Optional[str]
    domain_id: Optional[str]
    domain_name: Optional[str]
    version: int
    created_at: datetime
    updated_at: datetime


class TopologyDetail(CamelModel):
    id: str
    name: str
    description: Optional[str]
    domain_id: Optional[str]
    domain_name: Optional[str]
    version: int
    created_at: datetime
    updated_at: datetime
    stats: TopologyStats


class TopologyListResponse(CamelModel):
    code: int = 0
    data: dict[str, Any]
    message: str = "ok"


class TopologyDetailResponse(CamelModel):
    code: int = 0
    data: TopologyDetail
    message: str = "ok"


# --- Graph ---
class TopologyCanvasNode(CamelModel):
    node_id: str
    x: float
    y: float


class TopologyNode(CamelModel):
    id: str
    topology_id: str
    node_type_id: str
    name: str
    dn: Optional[str]
    status: str
    created_at: datetime
    updated_at: datetime


class TopologyEdge(CamelModel):
    id: str
    topology_id: str
    edge_type_id: str
    source_id: str
    target_id: str
    status: str
    created_at: datetime
    updated_at: datetime


class TopologyGraph(CamelModel):
    id: str
    name: str
    description: Optional[str]
    version: int
    nodes: list[TopologyNode]
    edges: list[TopologyEdge]
    canvas_nodes: list[TopologyCanvasNode]
