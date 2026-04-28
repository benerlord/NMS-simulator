import math
import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.db.connection import connect, transaction
from app.admin.schemas import (
    TOPOLOGY_IO_SCHEMA_VERSION,
    TopologyCreate,
    TopologyDetail,
    TopologyExportDoc,
    TopologyExportEdge,
    TopologyExportMeta,
    TopologyExportNode,
    TopologyExportResponse,
    TopologyGraph,
    TopologyImportResponse,
    TopologyImportResult,
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

    # Bulk write inside a single transaction. The DB connection runs in
    # autocommit mode (isolation_level=None), so per-row execute would fsync
    # on every write — the 30k-position canvas save measured 2887 ms before
    # this change. executemany inside one transaction collapses it to a
    # single fsync at COMMIT.
    rows = [(id, n["node_id"], n["x"], n["y"]) for n in body.nodes]
    with transaction() as conn:
        conn.executemany(
            """
            INSERT OR REPLACE INTO canvas_nodes (topology_id, node_id, x, y)
            VALUES (?, ?, ?, ?)
            """,
            rows,
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


# ---------------------------------------------------------------------------
# M4-02 拓扑导入/导出
# ---------------------------------------------------------------------------

# GET /admin/api/topologies/{id}/export
@router.get("/topologies/{id}/export", response_model=TopologyExportResponse)
def export_topology(id: str) -> dict:
    with connect() as conn:
        topo = conn.execute(
            "SELECT id, name, description, version FROM topologies WHERE id = ?", (id,)
        ).fetchone()
        if not topo:
            raise HTTPException(
                status_code=404,
                detail={"code": 40101, "message": "拓扑不存在", "details": {"topologyId": id}},
            )

        node_rows = conn.execute(
            """
            SELECT n.id, n.name, n.dn, n.status, nt.code AS node_type_code
              FROM nodes n
              JOIN node_types nt ON nt.id = n.node_type_id
             WHERE n.topology_id = ?
            """,
            (id,),
        ).fetchall()
        node_attr_rows = conn.execute(
            """
            SELECT na.node_id, na.field_key, na.value
              FROM node_attrs na
              JOIN nodes n ON n.id = na.node_id
             WHERE n.topology_id = ?
            """,
            (id,),
        ).fetchall()
        canvas_rows = conn.execute(
            "SELECT node_id, x, y FROM canvas_nodes WHERE topology_id = ?", (id,)
        ).fetchall()
        edge_rows = conn.execute(
            """
            SELECT e.id, e.source_id, e.target_id, e.status, et.code AS edge_type_code
              FROM edges e
              JOIN edge_types et ON et.id = e.edge_type_id
             WHERE e.topology_id = ?
            """,
            (id,),
        ).fetchall()
        edge_attr_rows = conn.execute(
            """
            SELECT ea.edge_id, ea.field_key, ea.value
              FROM edge_attrs ea
              JOIN edges e ON e.id = ea.edge_id
             WHERE e.topology_id = ?
            """,
            (id,),
        ).fetchall()

    node_attrs: dict[str, dict] = {}
    for r in node_attr_rows:
        node_attrs.setdefault(r["node_id"], {})[r["field_key"]] = r["value"]

    canvas_by_node: dict[str, dict] = {
        r["node_id"]: {"x": float(r["x"]), "y": float(r["y"])} for r in canvas_rows
    }

    edge_attrs: dict[str, dict] = {}
    for r in edge_attr_rows:
        edge_attrs.setdefault(r["edge_id"], {})[r["field_key"]] = r["value"]

    nodes = [
        TopologyExportNode(
            id=r["id"],
            node_type_code=r["node_type_code"],
            name=r["name"],
            dn=r["dn"],
            status=r["status"],
            attrs=node_attrs.get(r["id"], {}),
            canvas=canvas_by_node.get(r["id"]),
        )
        for r in node_rows
    ]
    edges = [
        TopologyExportEdge(
            id=r["id"],
            edge_type_code=r["edge_type_code"],
            source_id=r["source_id"],
            target_id=r["target_id"],
            status=r["status"],
            attrs=edge_attrs.get(r["id"], {}),
        )
        for r in edge_rows
    ]

    doc = TopologyExportDoc(
        schema_version=TOPOLOGY_IO_SCHEMA_VERSION,
        exported_at=datetime.utcnow(),
        topology=TopologyExportMeta(
            name=topo["name"], description=topo["description"], version=topo["version"]
        ),
        nodes=nodes,
        edges=edges,
    )
    return {
        "code": 0,
        "data": doc.model_dump(mode="json", by_alias=True),
        "message": "ok",
    }


def _resolve_unique_name(conn, base_name: str) -> str:
    """Append " (导入 N)" when base_name already exists; N starts at empty (1)."""
    row = conn.execute(
        "SELECT 1 FROM topologies WHERE name = ?", (base_name,)
    ).fetchone()
    if not row:
        return base_name
    n = 1
    while True:
        candidate = f"{base_name} (导入{'' if n == 1 else f' {n}'})"
        row = conn.execute(
            "SELECT 1 FROM topologies WHERE name = ?", (candidate,)
        ).fetchone()
        if not row:
            return candidate
        n += 1


def _new_node_id() -> str:
    return f"node_{uuid.uuid4().hex[:12]}"


def _new_edge_id() -> str:
    return f"edge_{uuid.uuid4().hex[:12]}"


# POST /admin/api/topologies/import
@router.post("/topologies/import", response_model=TopologyImportResponse)
def import_topology(body: TopologyExportDoc) -> dict:
    if body.schema_version != TOPOLOGY_IO_SCHEMA_VERSION:
        raise HTTPException(
            status_code=400,
            detail={
                "code": 40010,
                "message": "schemaVersion 不兼容",
                "details": {
                    "expected": TOPOLOGY_IO_SCHEMA_VERSION,
                    "got": body.schema_version,
                },
            },
        )

    # Pre-flight: validate edge endpoints reference declared nodes + no self-loop
    node_id_set = {n.id for n in body.nodes}
    if len(node_id_set) != len(body.nodes):
        raise HTTPException(
            status_code=400,
            detail={"code": 40011, "message": "导入文档存在重复节点 id"},
        )
    edge_id_set = {e.id for e in body.edges}
    if len(edge_id_set) != len(body.edges):
        raise HTTPException(
            status_code=400,
            detail={"code": 40012, "message": "导入文档存在重复边 id"},
        )
    for e in body.edges:
        if e.source_id == e.target_id:
            raise HTTPException(
                status_code=400,
                detail={
                    "code": 40013,
                    "message": "边的 sourceId 和 targetId 不能相同（自环）",
                    "details": {"edgeId": e.id},
                },
            )
        if e.source_id not in node_id_set or e.target_id not in node_id_set:
            raise HTTPException(
                status_code=400,
                detail={
                    "code": 40014,
                    "message": "边引用了不存在的节点",
                    "details": {
                        "edgeId": e.id,
                        "sourceId": e.source_id,
                        "targetId": e.target_id,
                    },
                },
            )

    now = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    new_topo_id = _new_id()

    with transaction() as conn:
        # Resolve node_type code → id
        used_node_codes = {n.node_type_code for n in body.nodes}
        node_type_rows = conn.execute(
            f"SELECT id, code FROM node_types WHERE code IN ({','.join(['?'] * len(used_node_codes))})",
            tuple(used_node_codes),
        ).fetchall() if used_node_codes else []
        node_type_id_by_code = {r["code"]: r["id"] for r in node_type_rows}
        missing_node_codes = sorted(used_node_codes - node_type_id_by_code.keys())
        if missing_node_codes:
            raise HTTPException(
                status_code=400,
                detail={
                    "code": 40015,
                    "message": "目标实例缺少节点类型 code",
                    "details": {"missingNodeTypeCodes": missing_node_codes},
                },
            )

        # Resolve edge_type code → id
        used_edge_codes = {e.edge_type_code for e in body.edges}
        edge_type_rows = conn.execute(
            f"SELECT id, code FROM edge_types WHERE code IN ({','.join(['?'] * len(used_edge_codes))})",
            tuple(used_edge_codes),
        ).fetchall() if used_edge_codes else []
        edge_type_id_by_code = {r["code"]: r["id"] for r in edge_type_rows}
        missing_edge_codes = sorted(used_edge_codes - edge_type_id_by_code.keys())
        if missing_edge_codes:
            raise HTTPException(
                status_code=400,
                detail={
                    "code": 40016,
                    "message": "目标实例缺少边类型 code",
                    "details": {"missingEdgeTypeCodes": missing_edge_codes},
                },
            )

        final_name = _resolve_unique_name(conn, body.topology.name)

        conn.execute(
            """
            INSERT INTO topologies (id, name, description, version, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                new_topo_id,
                final_name,
                body.topology.description or "",
                body.topology.version or 1,
                now,
                now,
            ),
        )

        # Build remap: original node id → new node id
        node_id_remap: dict[str, str] = {}
        for n in body.nodes:
            new_id = _new_node_id()
            node_id_remap[n.id] = new_id
            conn.execute(
                """
                INSERT INTO nodes (id, topology_id, node_type_id, name, dn, status, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    new_id,
                    new_topo_id,
                    node_type_id_by_code[n.node_type_code],
                    n.name,
                    n.dn,
                    n.status,
                    now,
                    now,
                ),
            )
            for k, v in (n.attrs or {}).items():
                conn.execute(
                    "INSERT INTO node_attrs (node_id, field_key, value) VALUES (?, ?, ?)",
                    (new_id, k, None if v is None else str(v)),
                )
            if n.canvas is not None:
                conn.execute(
                    """
                    INSERT INTO canvas_nodes (node_id, topology_id, x, y)
                    VALUES (?, ?, ?, ?)
                    """,
                    (new_id, new_topo_id, n.canvas.get("x", 0.0), n.canvas.get("y", 0.0)),
                )

        canvas_count = conn.execute(
            "SELECT COUNT(*) FROM canvas_nodes WHERE topology_id = ?", (new_topo_id,)
        ).fetchone()[0]

        for e in body.edges:
            new_eid = _new_edge_id()
            conn.execute(
                """
                INSERT INTO edges (id, topology_id, edge_type_id, source_id, target_id, status, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    new_eid,
                    new_topo_id,
                    edge_type_id_by_code[e.edge_type_code],
                    node_id_remap[e.source_id],
                    node_id_remap[e.target_id],
                    e.status,
                    now,
                    now,
                ),
            )
            for k, v in (e.attrs or {}).items():
                conn.execute(
                    "INSERT INTO edge_attrs (edge_id, field_key, value) VALUES (?, ?, ?)",
                    (new_eid, k, None if v is None else str(v)),
                )

    result = TopologyImportResult(
        topology_id=new_topo_id,
        name=final_name,
        node_count=len(body.nodes),
        edge_count=len(body.edges),
        canvas_count=canvas_count,
    )
    return {
        "code": 0,
        "data": result.model_dump(mode="json", by_alias=True),
        "message": "ok",
    }
