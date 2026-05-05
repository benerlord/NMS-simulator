from datetime import datetime
from typing import Optional, Literal

from pydantic import Field, model_validator

from ._base import CamelModel


# --- Attr Strategy ---

class AttrStrategyItem(CamelModel):
    field_key: str = Field(..., min_length=1)
    strategy: Literal["fixed", "random", "increment", "range"]
    fixed_value: Optional[str] = None
    pool: Optional[list[str]] = None
    base: Optional[str] = None
    step: Optional[str] = None
    min: Optional[int] = None
    max: Optional[int] = None

    @model_validator(mode="after")
    def validate_strategy_params(self):
        if self.strategy == "fixed":
            if not self.fixed_value:
                raise ValueError("fixed 策略必须提供 fixedValue")
        elif self.strategy == "random":
            if not self.pool or len(self.pool) < 1:
                raise ValueError("random 策略必须提供 pool 且至少包含 1 个值")
        elif self.strategy == "increment":
            if self.base is None or self.step is None:
                raise ValueError("increment 策略必须提供 base 和 step")
        elif self.strategy == "range":
            if self.min is None or self.max is None:
                raise ValueError("range 策略必须提供 min 和 max")
        return self


# --- Edge Strategy ---

class EdgeStrategyItem(CamelModel):
    target_group_id: str = Field(..., min_length=1)
    edge_type_code: str = Field(..., min_length=1)
    mode: Literal["modulo", "one_to_n", "all_to_all", "dense"]
    ratio_k: Optional[int] = None

    @model_validator(mode="after")
    def validate_mode_params(self):
        if self.mode in ("modulo", "one_to_n"):
            if self.ratio_k is None or self.ratio_k <= 0:
                raise ValueError(f"{self.mode} 模式必须提供 ratioK 且 > 0")
        return self


# --- NodeGroup CRUD ---

class NodeGroupCreate(CamelModel):
    node_type_id: str = Field(..., min_length=1)
    group_name: str = Field(..., min_length=1, max_length=200)
    node_count: int = Field(..., ge=1, le=1_000_000)
    name_template: str = Field(default="{group}-{i:05d}", max_length=200)
    attr_strategies: list[AttrStrategyItem] = []
    edge_strategies: Optional[list[EdgeStrategyItem]] = None


class NodeGroupUpdate(CamelModel):
    group_name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    node_count: Optional[int] = Field(default=None, ge=1, le=1_000_000)
    name_template: Optional[str] = None
    attr_strategies: Optional[list[AttrStrategyItem]] = None
    edge_strategies: Optional[list[EdgeStrategyItem]] = None


class NodeGroupItem(CamelModel):
    id: str
    topology_id: str
    node_type_id: str
    group_name: str
    node_count: int
    name_template: str
    attr_strategies: list[AttrStrategyItem]
    edge_strategies: Optional[list[EdgeStrategyItem]]
    is_materialized: bool
    created_at: datetime
    updated_at: datetime


# --- Group Graph (for canvas rendering) ---

class MacroNodeStatus(CamelModel):
    online: int = 0
    offline: int = 0


class MacroNode(CamelModel):
    id: str
    topology_id: str
    node_type_id: str
    group_name: str
    node_count: int
    is_materialized: bool
    status_breakdown: MacroNodeStatus
    x: Optional[float] = None
    y: Optional[float] = None


class MacroEdge(CamelModel):
    source_group_id: str
    target_group_id: str
    edge_type_code: str
    mode: str
    ratio_k: Optional[int] = None
    total_edge_count: int
    visual_source_is_macro: Optional[bool] = None


class GroupGraphData(CamelModel):
    macro_nodes: list[MacroNode]
    macro_edges: list[MacroEdge]
