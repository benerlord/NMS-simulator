import math
import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.db.connection import connect, transaction
from app.admin.schemas import (
    TopologyCreate,
    TopologyDetail,
    TopologyGraph,
    TopologyListItem,
    TopologyStats,
    TopologyUpdate,
)

router = APIRouter(prefix="/admin/api", tags=["拓扑"])


def _new_id() -> str:
    return f"topo_{uuid.uuid4().hex[:12]}"


def _row_to_list_item(row) -> TopologyListItem:
    return TopologyListItem(
        id=row["id"],
        name=row["name"],
        description=row["description"],
        version=row["version"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _row_to_detail(row, stats: TopologyStats) -> TopologyDetail:
    return TopologyDetail(
        id=row["id"],
        name=row["name"],
        description=row["description"],
        version=row["version"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        stats=stats,
    )


def _topology_stats(conn, topo_id: str) -> TopologyStats:
    node_count = conn.execute(
        "SELECT COUNT(*) FROM nodes WHERE topology_id = ?", (topo_id,)
    ).fetchone()[0]
    edge_count = conn.execute(
        "SELECT COUNT(*) FROM edges WHERE topology_id = ?", (topo_id,)
    ).fetchone()[0]
    return TopologyStats(node_count=node_count, edge_count=edge_count)


class ListResponse(BaseModel):
    code: int = 0
    data: dict
    message: str = "ok"


class DetailResponse(BaseModel):
    code: int = 0
    data: TopologyDetail
    message: str = "ok"


class GraphResponse(BaseModel):
    code: int = 0
    data: TopologyGraph
    message: str = "ok"


# DELETE /admin/api/topologies (批量删除全部)
@router.delete("/topologies")
def delete_all_topologies() -> dict:
    with connect() as conn:
        # 查找被 api_configs 引用的拓扑
        ref_rows = conn.execute(
            "SELECT DISTINCT topology_id FROM api_configs WHERE topology_id IS NOT NULL"
        ).fetchall()
        if ref_rows:
            referenced_ids = [r["topology_id"] for r in ref_rows]
            return {
                "code": 40103,
                "message": "部分拓扑被接口配置引用，无法删除",
                "details": {"referencedTopologyIds": referenced_ids},
            }

        # 先删除关联的节点、边、画布数据
        topo_rows = conn.execute("SELECT id FROM topologies").fetchall()
        topo_ids = [r["id"] for r in topo_rows]
        if not topo_ids:
            return {"code": 0, "data": {"deletedCount": 0}, "message": "无拓扑可删除"}

        deleted_count = len(topo_ids)
        for topo_id in topo_ids:
            conn.execute("DELETE FROM canvas_nodes WHERE topology_id = ?", (topo_id,))
            conn.execute("DELETE FROM edges WHERE topology_id = ?", (topo_id,))
            conn.execute("DELETE FROM nodes WHERE topology_id = ?", (topo_id,))
        conn.execute("DELETE FROM topologies")
    return {"code": 0, "data": {"deletedCount": deleted_count}, "message": "删除成功"}


# GET /admin/api/topologies
@router.get("/topologies", response_model=ListResponse)
def list_topologies(
    name: Optional[str] = Query(None, description="名称模糊过滤"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=500),
    sort: str = Query("updated_at,desc"),
) -> dict:
    order_field, order_dir = (sort.split(",") if "," in sort else ["updated_at", "desc"])
    order_field = order_field if order_field in ("name", "created_at", "updated_at") else "updated_at"
    order_dir = order_dir.upper() if order_dir.upper() in ("ASC", "DESC") else "DESC"
    offset = (page - 1) * page_size

    with connect() as conn:
        where = "WHERE name LIKE ?" if name else ""
        params = [f"%{name}%"] if name else []
        total = conn.execute(
            f"SELECT COUNT(*) FROM topologies {where}", params
        ).fetchone()[0]
        rows = conn.execute(
            f"""
            SELECT * FROM topologies {where}
            ORDER BY {order_field} {order_dir}
            LIMIT ? OFFSET ?
            """,
            params + [page_size, offset],
        ).fetchall()

    items = [_row_to_list_item(r) for r in rows]
    return ListResponse(
        data={
            "items": [m.model_dump(mode="json", by_alias=True) for m in items],
            "total": total,
            "page": page,
            "pageSize": page_size,
        }
    )


# GET /admin/api/topologies/{id}
@router.get("/topologies/{id}", response_model=DetailResponse)
def get_topology(id: str) -> dict:
    with connect() as conn:
        row = conn.execute(
            "SELECT * FROM topologies WHERE id = ?", (id,)
        ).fetchone()
        if not row:
            raise HTTPException(
                status_code=404,
                detail={"code": 40101, "message": "拓扑不存在", "details": {"topologyId": id}},
            )
        stats = _topology_stats(conn, id)
        detail = _row_to_detail(row, stats)
    return DetailResponse(data=detail)


# POST /admin/api/topologies
@router.post("/topologies", response_model=DetailResponse)
def create_topology(body: TopologyCreate) -> dict:
    topo_id = _new_id()
    now = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    with transaction() as conn:
        existing = conn.execute(
            "SELECT id FROM topologies WHERE name = ?", (body.name,)
        ).fetchone()
        if existing:
            raise HTTPException(
                status_code=409,
                detail={"code": 40003, "message": "拓扑名称已存在", "details": {"name": body.name}},
            )
        conn.execute(
            """
            INSERT INTO topologies (id, name, description, version, created_at, updated_at)
            VALUES (?, ?, ?, 1, ?, ?)
            """,
            (topo_id, body.name, body.description or "", now, now),
        )
        row = conn.execute(
            "SELECT * FROM topologies WHERE id = ?", (topo_id,)
        ).fetchone()
        detail = _row_to_detail(row, TopologyStats(node_count=0, edge_count=0))
    return DetailResponse(data=detail)


# PUT /admin/api/topologies/{id}
@router.put("/topologies/{id}", response_model=DetailResponse)
def update_topology(id: str, body: TopologyUpdate) -> dict:
    with connect() as conn:
        row = conn.execute(
            "SELECT * FROM topologies WHERE id = ?", (id,)
        ).fetchone()
        if not row:
            raise HTTPException(
                status_code=404,
                detail={"code": 40101, "message": "拓扑不存在", "details": {"topologyId": id}},
            )

    updates, params = [], []
    if body.name is not None:
        updates.append("name = ?")
        params.append(body.name)
    if body.description is not None:
        updates.append("description = ?")
        params.append(body.description)
    if not updates:
        raise HTTPException(
            status_code=400,
            detail={"code": 40001, "message": "无更新字段", "details": []},
        )

    updates.append("updated_at = ?")
    params.append(datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"))
    params.append(id)

    with transaction() as conn:
        conn.execute(
            f"UPDATE topologies SET {', '.join(updates)} WHERE id = ?",
            params,
        )
        row = conn.execute(
            "SELECT * FROM topologies WHERE id = ?", (id,)
        ).fetchone()
        stats = _topology_stats(conn, id)
        detail = _row_to_detail(row, stats)
    return DetailResponse(data=detail)


# DELETE /admin/api/topologies/{id}
@router.delete("/topologies/{id}")
def delete_topology(id: str) -> dict:
    with connect() as conn:
        row = conn.execute(
            "SELECT id FROM topologies WHERE id = ?", (id,)
        ).fetchone()
        if not row:
            raise HTTPException(
                status_code=404,
                detail={"code": 40101, "message": "拓扑不存在", "details": {"topologyId": id}},
            )

        ref = conn.execute(
            "SELECT id FROM api_configs WHERE topology_id = ? LIMIT 1", (id,)
        ).fetchone()
        if ref:
            return {
                "code": 40103,
                "message": "拓扑被接口配置引用，无法删除",
                "details": {"topologyId": id},
            }

    with transaction() as conn:
        conn.execute("DELETE FROM topologies WHERE id = ?", (id,))
    return {"code": 0, "data": None, "message": "删除成功"}


class CanvasPositionsRequest(BaseModel):
    nodes: list[dict]  # [{node_id: str, x: float, y: float}]


# PATCH /admin/api/topologies/{id}/canvas
@router.patch("/topologies/{id}/canvas")
async def save_canvas_positions(id: str, body: CanvasPositionsRequest) -> dict:
    with connect() as conn:
        row = conn.execute(
            "SELECT id FROM topologies WHERE id = ?", (id,)
        ).fetchone()
        if not row:
            raise HTTPException(
                status_code=404,
                detail={"code": 40101, "message": "拓扑不存在", "details": {"topologyId": id}},
            )

        for node in body.nodes:
            conn.execute(
                """
                INSERT OR REPLACE INTO canvas_nodes (topology_id, node_id, x, y)
                VALUES (?, ?, ?, ?)
                """,
                (id, node["node_id"], node["x"], node["y"]),
            )

    from app.core.ws_hub import broadcast_topology_saved
    await broadcast_topology_saved(id)

    return {"code": 0, "data": None, "message": "保存成功"}


# GET /admin/api/topologies/{id}/graph
@router.get("/topologies/{id}/graph", response_model=GraphResponse)
def get_topology_graph(id: str) -> dict:
    with connect() as conn:
        row = conn.execute(
            "SELECT * FROM topologies WHERE id = ?", (id,)
        ).fetchone()
        if not row:
            raise HTTPException(
                status_code=404,
                detail={"code": 40101, "message": "拓扑不存在", "details": {"topologyId": id}},
            )

        node_rows = conn.execute(
            "SELECT * FROM nodes WHERE topology_id = ?", (id,)
        ).fetchall()
        edge_rows = conn.execute(
            "SELECT * FROM edges WHERE topology_id = ?", (id,)
        ).fetchall()
        canvas_rows = conn.execute(
            "SELECT * FROM canvas_nodes WHERE topology_id = ?", (id,)
        ).fetchall()

    def _parse_dt(val) -> datetime:
        if isinstance(val, str):
            return datetime.fromisoformat(val.replace("Z", "+00:00"))
        return val

    nodes = [
        {
            "id": r["id"],
            "topology_id": r["topology_id"],
            "node_type_id": r["node_type_id"],
            "name": r["name"],
            "dn": r["dn"],
            "status": r["status"],
            "created_at": _parse_dt(r["created_at"]),
            "updated_at": _parse_dt(r["updated_at"]),
        }
        for r in node_rows
    ]
    edges = [
        {
            "id": r["id"],
            "topology_id": r["topology_id"],
            "edge_type_id": r["edge_type_id"],
            "source_id": r["source_id"],
            "target_id": r["target_id"],
            "status": r["status"],
            "created_at": _parse_dt(r["created_at"]),
            "updated_at": _parse_dt(r["updated_at"]),
        }
        for r in edge_rows
    ]
    canvas_nodes = [
        {"node_id": r["node_id"], "x": r["x"], "y": r["y"]}
        for r in canvas_rows
    ]

    graph = TopologyGraph(
        id=row["id"],
        name=row["name"],
        description=row["description"],
        version=row["version"],
        nodes=nodes,
        edges=edges,
        canvas_nodes=canvas_nodes,
    )
    return GraphResponse(data=graph)
