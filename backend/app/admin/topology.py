import math
import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from pydantic import BaseModel

from app.db.connection import connect, transaction
from app.admin.schemas import (
    TOPOLOGY_IO_SCHEMA_VERSION,
    TopologyAlarmSchemaPatch,
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


def _now() -> str:
    """ISO-8601 UTC timestamp ending with Z (matches api_config.py format)."""
    return datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")


def _row_to_list_item(row) -> TopologyListItem:
    return TopologyListItem(
        id=row["id"],
        name=row["name"],
        description=row["description"],
        domain_id=row["domain_id"] if "domain_id" in row.keys() else None,
        domain_name=row["domain_name"] if "domain_name" in row.keys() else None,
        version=row["version"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _row_to_detail(
    row,
    stats: TopologyStats,
    alarm_schema_id: Optional[str] = None,
    node_alarm_count: int = 0,
) -> TopologyDetail:
    return TopologyDetail(
        id=row["id"],
        name=row["name"],
        description=row["description"],
        domain_id=row["domain_id"] if "domain_id" in row.keys() else None,
        domain_name=row["domain_name"] if "domain_name" in row.keys() else None,
        version=row["version"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        stats=stats,
        alarm_schema_id=alarm_schema_id,
        node_alarm_count=node_alarm_count,
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
    with transaction() as conn:
        topo_rows = conn.execute("SELECT id FROM topologies").fetchall()
        topo_ids = [r["id"] for r in topo_rows]
        if not topo_ids:
            return {"code": 0, "data": {"deletedCount": 0, "unboundApiCount": 0}, "message": "无拓扑可删除"}

        # LEGACY-07: 应用层主动解绑 api_configs（FK 保留 NO ACTION 兜底）
        unbound = conn.execute(
            "UPDATE api_configs SET topology_id = NULL, updated_at = ? "
            "WHERE topology_id IS NOT NULL",
            (_now(),),
        )
        unbound_count = unbound.rowcount

        # 删除关联的节点、边、画布数据
        for topo_id in topo_ids:
            conn.execute("DELETE FROM canvas_nodes WHERE topology_id = ?", (topo_id,))
            conn.execute("DELETE FROM edges WHERE topology_id = ?", (topo_id,))
            conn.execute("DELETE FROM nodes WHERE topology_id = ?", (topo_id,))
        conn.execute("DELETE FROM topologies")
    return {
        "code": 0,
        "data": {"deletedCount": len(topo_ids), "unboundApiCount": unbound_count},
        "message": "删除成功",
    }


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
            SELECT t.*, d.name AS domain_name
            FROM topologies t
            LEFT JOIN domains d ON d.id = t.domain_id
            {where}
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
        row = conn.execute("""
            SELECT t.*, d.name AS domain_name
            FROM topologies t
            LEFT JOIN domains d ON d.id = t.domain_id
            WHERE t.id = ?
        """, (id,)).fetchone()
        if not row:
            raise HTTPException(
                status_code=404,
                detail={"code": 40101, "message": "拓扑不存在", "details": {"topologyId": id}},
            )
        stats = _topology_stats(conn, id)
        alarm_schema_id = row["alarm_schema_id"]
        node_alarm_count = 0
        if alarm_schema_id:
            node_alarm_count = conn.execute(
                "SELECT COUNT(*) AS c FROM node_alarms a "
                "JOIN nodes n ON n.id = a.node_id WHERE n.topology_id = ?",
                (id,),
            ).fetchone()["c"]
        detail = _row_to_detail(row, stats, alarm_schema_id=alarm_schema_id, node_alarm_count=node_alarm_count)
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
            INSERT INTO topologies (id, name, description, domain_id, version, created_at, updated_at)
            VALUES (?, ?, ?, ?, 1, ?, ?)
            """,
            (topo_id, body.name, body.description or "", body.domain_id, now, now),
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
    if "domain_id" in body.model_fields_set:
        updates.append("domain_id = ?")
        params.append(body.domain_id)
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
    with transaction() as conn:
        row = conn.execute(
            "SELECT id FROM topologies WHERE id = ?", (id,)
        ).fetchone()
        if not row:
            raise HTTPException(
                status_code=404,
                detail={"code": 40101, "message": "拓扑不存在", "details": {"topologyId": id}},
            )

        # LEGACY-07: 应用层主动解绑 api_configs（FK 保留 NO ACTION 兜底）
        unbound = conn.execute(
            "UPDATE api_configs SET topology_id = NULL, updated_at = ? WHERE topology_id = ?",
            (_now(), id),
        )
        unbound_count = unbound.rowcount

        conn.execute("DELETE FROM canvas_nodes WHERE topology_id = ?", (id,))
        conn.execute("DELETE FROM edges WHERE topology_id = ?", (id,))
        conn.execute("DELETE FROM nodes WHERE topology_id = ?", (id,))
        conn.execute("DELETE FROM topologies WHERE id = ?", (id,))
    return {
        "code": 0,
        "data": {"unboundApiCount": unbound_count},
        "message": "删除成功",
    }


# GET /admin/api/topologies/{id}/delete-impact (LEGACY-07: 删除前预扫描)
@router.get("/topologies/{id}/delete-impact")
def get_topology_delete_impact(id: str) -> dict:
    with connect() as conn:
        row = conn.execute(
            "SELECT id, name FROM topologies WHERE id = ?", (id,)
        ).fetchone()
        if not row:
            raise HTTPException(
                status_code=404,
                detail={"code": 40101, "message": "拓扑不存在", "details": {"topologyId": id}},
            )
        # 受影响接口总数（精确）
        count_row = conn.execute(
            "SELECT COUNT(*) AS n FROM api_configs WHERE topology_id = ?", (id,)
        ).fetchone()
        affected_count = int(count_row["n"]) if count_row else 0
        # 取前 50 个接口的展示信息
        api_rows = conn.execute(
            "SELECT id, name, method, path FROM api_configs "
            "WHERE topology_id = ? ORDER BY name LIMIT 50",
            (id,),
        ).fetchall()
        affected_apis = [
            {
                "id": r["id"],
                "name": r["name"],
                "method": r["method"],
                "path": r["path"],
            }
            for r in api_rows
        ]
    return {
        "code": 0,
        "data": {
            "topologyId": row["id"],
            "topologyName": row["name"],
            "affectedApiCount": affected_count,
            "affectedApis": affected_apis,
        },
        "message": "ok",
    }


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


# PATCH /admin/api/topologies/{topology_id}/alarm-schema
@router.patch("/topologies/{topology_id}/alarm-schema")
def bind_alarm_schema(topology_id: str, data: TopologyAlarmSchemaPatch) -> dict:
    with transaction() as conn:
        row = conn.execute(
            "SELECT id, alarm_schema_id FROM topologies WHERE id = ?", (topology_id,)
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail={"code": 40404, "message": "拓扑不存在"})

        new_sid = data.alarm_schema_id or None
        current_sid = row["alarm_schema_id"]

        # Verify schema exists if binding (not unbinding)
        if new_sid:
            schema = conn.execute(
                "SELECT id FROM alarm_schemas WHERE id = ?", (new_sid,)
            ).fetchone()
            if not schema:
                raise HTTPException(status_code=404, detail={"code": 40404, "message": "告警模板不存在"})

        # Check alarm count when changing (incl. unbinding)
        if new_sid != current_sid:
            cnt_row = conn.execute(
                "SELECT COUNT(*) AS c FROM node_alarms a "
                "JOIN nodes n ON n.id = a.node_id "
                "WHERE n.topology_id = ?",
                (topology_id,),
            ).fetchone()
            alarm_cnt = cnt_row["c"]
            if alarm_cnt > 0 and not data.clear_existing:
                raise HTTPException(
                    status_code=409,
                    detail={
                        "code": 40902,
                        "message": "拓扑下有告警数据，请确认是否清空",
                        "details": {"nodeAlarmCount": alarm_cnt},
                    },
                )
            if alarm_cnt > 0 and data.clear_existing:
                conn.execute(
                    "DELETE FROM node_alarms WHERE node_id IN "
                    "(SELECT id FROM nodes WHERE topology_id = ?)",
                    (topology_id,),
                )

        conn.execute(
            "UPDATE topologies SET alarm_schema_id = ?, updated_at = datetime('now') WHERE id = ?",
            (new_sid, topology_id),
        )

    return {"code": 0, "data": {"alarmSchemaId": new_sid}, "message": "ok"}


# ---------------------------------------------------------------------------
# 画布 Excel 导出 / 导入
# ---------------------------------------------------------------------------

@router.get("/topologies/{id}/export-excel")
def export_topology_excel(id: str):
    """导出拓扑为 Excel (.xlsx)"""
    import io as _io
    from fastapi.responses import Response
    from app.admin._topology_excel import build_workbook

    with connect() as conn:
        topo = conn.execute(
            "SELECT t.name, t.description, t.version, d.name AS domain_name, "
            "s.code AS alarm_schema_code "
            "FROM topologies t "
            "LEFT JOIN domains d ON d.id = t.domain_id "
            "LEFT JOIN alarm_schemas s ON s.id = t.alarm_schema_id "
            "WHERE t.id = ?", (id,)
        ).fetchone()
        if not topo:
            raise HTTPException(
                status_code=404,
                detail={"code": 40101, "message": "拓扑不存在"},
            )
        topology_meta = {
            "name": topo["name"],
            "description": topo["description"],
            "version": topo["version"],
            "domain_name": topo["domain_name"],
            "alarm_schema_code": topo["alarm_schema_code"],
        }

        nt_rows = conn.execute(
            "SELECT DISTINCT nt.id, nt.code, nt.name FROM nodes n "
            "JOIN node_types nt ON nt.id = n.node_type_id "
            "WHERE n.topology_id = ?", (id,)
        ).fetchall()
        node_types = []
        for nt in nt_rows:
            fields = conn.execute(
                "SELECT field_key FROM node_type_fields "
                "WHERE node_type_id = ? ORDER BY sort_order, id", (nt["id"],)
            ).fetchall()
            node_types.append({
                "id": nt["id"], "code": nt["code"], "name": nt["name"],
                "fields": [{"field_key": f["field_key"]} for f in fields],
            })

        et_rows = conn.execute(
            "SELECT DISTINCT et.id, et.code, et.name FROM edges e "
            "JOIN edge_types et ON et.id = e.edge_type_id "
            "WHERE e.topology_id = ?", (id,)
        ).fetchall()
        edge_types = []
        for et in et_rows:
            fields = conn.execute(
                "SELECT field_key FROM edge_type_fields "
                "WHERE edge_type_id = ? ORDER BY sort_order, id", (et["id"],)
            ).fetchall()
            edge_types.append({
                "id": et["id"], "code": et["code"], "name": et["name"],
                "fields": [{"field_key": f["field_key"]} for f in fields],
            })

        nodes_by_type_code: dict = {nt["code"]: [] for nt in node_types}
        node_rows = conn.execute(
            "SELECT n.id, n.name, n.dn, n.status, nt.code AS node_type_code, "
            "cn.x AS canvas_x, cn.y AS canvas_y, g.group_name "
            "FROM nodes n "
            "JOIN node_types nt ON nt.id = n.node_type_id "
            "LEFT JOIN canvas_nodes cn ON cn.node_id = n.id "
            "LEFT JOIN node_groups g ON g.id = n.group_id "
            "WHERE n.topology_id = ?", (id,)
        ).fetchall()
        node_attrs = {}
        for r in conn.execute(
            "SELECT na.node_id, na.field_key, na.value FROM node_attrs na "
            "JOIN nodes n ON n.id = na.node_id WHERE n.topology_id = ?", (id,)
        ).fetchall():
            node_attrs.setdefault(r["node_id"], {})[r["field_key"]] = r["value"]
        for r in node_rows:
            nodes_by_type_code[r["node_type_code"]].append({
                "id": r["id"], "name": r["name"], "dn": r["dn"], "status": r["status"],
                "canvas_x": r["canvas_x"], "canvas_y": r["canvas_y"],
                "group_name": r["group_name"],
                "attrs": node_attrs.get(r["id"], {}),
            })

        edges_by_type_code: dict = {et["code"]: [] for et in edge_types}
        edge_rows = conn.execute(
            "SELECT e.id, e.source_id, e.target_id, e.status, et.code AS edge_type_code "
            "FROM edges e JOIN edge_types et ON et.id = e.edge_type_id "
            "WHERE e.topology_id = ?", (id,)
        ).fetchall()
        edge_attrs = {}
        for r in conn.execute(
            "SELECT ea.edge_id, ea.field_key, ea.value FROM edge_attrs ea "
            "JOIN edges e ON e.id = ea.edge_id WHERE e.topology_id = ?", (id,)
        ).fetchall():
            edge_attrs.setdefault(r["edge_id"], {})[r["field_key"]] = r["value"]
        for r in edge_rows:
            edges_by_type_code[r["edge_type_code"]].append({
                "id": r["id"], "source_id": r["source_id"], "target_id": r["target_id"],
                "status": r["status"], "attrs": edge_attrs.get(r["id"], {}),
            })

        import json
        group_rows = conn.execute(
            "SELECT id, group_name, node_type_id, node_count, name_template, "
            "attr_strategies, edge_strategies, canvas_x, canvas_y "
            "FROM node_groups WHERE topology_id = ?", (id,)
        ).fetchall()
        node_groups = []
        node_group_edge_strategies = []
        group_id_to_name = {}
        for g in group_rows:
            attrs = json.loads(g["attr_strategies"]) if g["attr_strategies"] else []
            node_groups.append({
                "id": g["id"], "group_name": g["group_name"],
                "node_type_id": g["node_type_id"], "node_count": g["node_count"],
                "name_template": g["name_template"],
                "materialized_at": None,
                "canvas_x": g["canvas_x"], "canvas_y": g["canvas_y"],
                "attr_strategies": attrs,
            })
            group_id_to_name[g["id"]] = g["group_name"]

        node_id_to_name = {r["id"]: r["name"] for r in node_rows}
        for g in group_rows:
            if not g["edge_strategies"]:
                continue
            for es in json.loads(g["edge_strategies"]):
                target_id = es.get("target_group_id")
                if target_id in group_id_to_name:
                    tname = group_id_to_name[target_id]
                    tkind = "组"
                elif target_id in node_id_to_name:
                    tname = node_id_to_name[target_id]
                    tkind = "节点"
                else:
                    tname = target_id
                    tkind = "组"
                node_group_edge_strategies.append({
                    "source_group_name": g["group_name"],
                    "target_name": tname,
                    "target_kind": tkind,
                    "edge_type_code": es.get("edge_type_code"),
                    "mode": es.get("mode"),
                    "ratio_k": es.get("ratio_k"),
                })

        alarm_schema_fields = []
        node_alarms = []
        node_group_alarms = []
        if topo["alarm_schema_code"]:
            sid_row = conn.execute(
                "SELECT id FROM alarm_schemas WHERE code = ?",
                (topo["alarm_schema_code"],)
            ).fetchone()
            if sid_row:
                sid = sid_row["id"]
                alarm_schema_fields = [dict(r) for r in conn.execute(
                    "SELECT field_key, mapping_target FROM alarm_schema_fields "
                    "WHERE alarm_schema_id = ? ORDER BY sort_order, id", (sid,)
                ).fetchall()]

                node_alarm_rows = conn.execute(
                    "SELECT a.id, a.node_id, a.alarm_index, n.node_type_id "
                    "FROM node_alarms a JOIN nodes n ON n.id = a.node_id "
                    "WHERE n.topology_id = ?", (id,)
                ).fetchall()
                node_alarm_attrs = {}
                for r in conn.execute(
                    "SELECT aa.alarm_id, aa.field_key, aa.value "
                    "FROM node_alarm_attrs aa "
                    "JOIN node_alarms a ON a.id = aa.alarm_id "
                    "JOIN nodes n ON n.id = a.node_id "
                    "WHERE n.topology_id = ?", (id,)
                ).fetchall():
                    node_alarm_attrs.setdefault(r["alarm_id"], {})[r["field_key"]] = r["value"]
                for r in node_alarm_rows:
                    node_alarms.append({
                        "node_id": r["node_id"],
                        "node_type_id": r["node_type_id"],
                        "alarm_index": r["alarm_index"],
                        "attrs": node_alarm_attrs.get(r["id"], {}),
                    })

                group_alarm_rows = conn.execute(
                    "SELECT ga.id, ga.node_group_id, ga.alarm_index "
                    "FROM node_group_alarms ga "
                    "JOIN node_groups g ON g.id = ga.node_group_id "
                    "WHERE g.topology_id = ?", (id,)
                ).fetchall()
                group_alarm_attrs = {}
                for r in conn.execute(
                    "SELECT gaa.alarm_id, gaa.field_key, gaa.value "
                    "FROM node_group_alarm_attrs gaa "
                    "JOIN node_group_alarms ga ON ga.id = gaa.alarm_id "
                    "JOIN node_groups g ON g.id = ga.node_group_id "
                    "WHERE g.topology_id = ?", (id,)
                ).fetchall():
                    group_alarm_attrs.setdefault(r["alarm_id"], {})[r["field_key"]] = r["value"]
                for r in group_alarm_rows:
                    node_group_alarms.append({
                        "node_group_id": r["node_group_id"],
                        "alarm_index": r["alarm_index"],
                        "attrs": group_alarm_attrs.get(r["id"], {}),
                    })

    wb = build_workbook(
        topology=topology_meta,
        node_types=node_types,
        edge_types=edge_types,
        nodes_by_type_code=nodes_by_type_code,
        edges_by_type_code=edges_by_type_code,
        node_groups=node_groups,
        node_group_edge_strategies=node_group_edge_strategies,
        alarm_schema_fields=alarm_schema_fields,
        node_alarms=node_alarms,
        node_group_alarms=node_group_alarms,
    )
    buf = _io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    # RFC 5987：文件名含非 ASCII（如中文拓扑名）时必须 UTF-8 百分号编码
    # 塞进 filename*；同时给一份 ASCII fallback filename= 兼容老客户端
    from urllib.parse import quote
    raw_name = f"topology-{topology_meta['name']}.xlsx"
    ascii_fallback = raw_name.encode("ascii", "ignore").decode("ascii") or "topology.xlsx"
    content_disposition = (
        f'attachment; filename="{ascii_fallback}"; '
        f"filename*=UTF-8''{quote(raw_name)}"
    )
    return Response(
        content=buf.getvalue(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": content_disposition},
    )


@router.post("/topologies/import-excel")
async def import_topology_excel(file: UploadFile = File(...)) -> dict:
    """从 Excel (.xlsx) 导入拓扑。始终新建。"""
    import io as _io
    import json
    from app.admin._topology_excel import parse_workbook, ExcelValidationError

    if not file.filename or not file.filename.lower().endswith(".xlsx"):
        raise HTTPException(
            status_code=400,
            detail={"code": 40410, "message": "仅支持 .xlsx 文件"},
        )
    contents = await file.read()
    try:
        parse = parse_workbook(_io.BytesIO(contents))
    except ExcelValidationError as e:
        raise HTTPException(
            status_code=400,
            detail={"code": 40411, "message": str(e)},
        )

    with transaction() as conn:
        new_name = _resolve_unique_name(conn, parse.meta["name"])

        domain_id = None
        domain_name = parse.meta.get("domain_name")
        if domain_name:
            row = conn.execute("SELECT id FROM domains WHERE name = ?", (domain_name,)).fetchone()
            if row:
                domain_id = row["id"]
            else:
                domain_id = f"dom_{uuid.uuid4().hex[:12]}"
                conn.execute(
                    "INSERT INTO domains (id, name, description) VALUES (?, ?, ?)",
                    (domain_id, domain_name, "导入时自动创建"),
                )
                parse.warnings.append(f"自动创建了网管 '{domain_name}'")

        alarm_schema_id = None
        alarm_schema_code = parse.meta.get("alarm_schema_code")
        if alarm_schema_code:
            row = conn.execute(
                "SELECT id FROM alarm_schemas WHERE code = ?", (alarm_schema_code,)
            ).fetchone()
            if not row:
                raise HTTPException(
                    status_code=400,
                    detail={"code": 40430, "message": f"告警模板 '{alarm_schema_code}' 不存在"},
                )
            alarm_schema_id = row["id"]

        for code in parse.nodes_by_type_code.keys():
            r = conn.execute("SELECT id FROM node_types WHERE code = ?", (code,)).fetchone()
            if not r:
                raise HTTPException(
                    status_code=400,
                    detail={"code": 40431, "message": f"节点类型代码 '{code}' 不存在"},
                )

        for code in parse.edges_by_type_code.keys():
            r = conn.execute("SELECT id FROM edge_types WHERE code = ?", (code,)).fetchone()
            if not r:
                raise HTTPException(
                    status_code=400,
                    detail={"code": 40431, "message": f"边类型代码 '{code}' 不存在"},
                )

        for code, nodes in parse.nodes_by_type_code.items():
            names = [n["name"] for n in nodes]
            if len(names) != len(set(names)):
                dup_names = [n for n in names if names.count(n) > 1]
                raise HTTPException(
                    status_code=400,
                    detail={"code": 40432,
                            "message": f"节点类型 '{code}' 下节点名重复：{sorted(set(dup_names))}"},
                )

        topology_id = f"topo_{uuid.uuid4().hex[:12]}"
        conn.execute(
            "INSERT INTO topologies (id, name, description, version, domain_id, alarm_schema_id) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (topology_id, new_name, parse.meta.get("description"),
             parse.meta.get("version") or 1, domain_id, alarm_schema_id),
        )

        node_id_by_name_type: dict = {}
        for code, nodes in parse.nodes_by_type_code.items():
            nt = conn.execute("SELECT id FROM node_types WHERE code = ?", (code,)).fetchone()
            for n in nodes:
                nid = f"node_{uuid.uuid4().hex[:12]}"
                conn.execute(
                    "INSERT INTO nodes (id, topology_id, node_type_id, name, dn, status) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (nid, topology_id, nt["id"], n["name"], n.get("dn"),
                     n.get("status") or "online"),
                )
                node_id_by_name_type[(code, n["name"])] = nid
                for k, v in (n.get("attrs") or {}).items():
                    conn.execute(
                        "INSERT INTO node_attrs (node_id, field_key, value) VALUES (?, ?, ?)",
                        (nid, k, str(v) if v is not None else None),
                    )
                if n.get("canvas_x") is not None and n.get("canvas_y") is not None:
                    conn.execute(
                        "INSERT INTO canvas_nodes (topology_id, node_id, x, y) "
                        "VALUES (?, ?, ?, ?)",
                        (topology_id, nid, float(n["canvas_x"]), float(n["canvas_y"])),
                    )

        for code, edges in parse.edges_by_type_code.items():
            et = conn.execute("SELECT id FROM edge_types WHERE code = ?", (code,)).fetchone()
            for e in edges:
                src_id = None
                tgt_id = None
                for (c, name), nid in node_id_by_name_type.items():
                    if name == e["source_name"] and src_id is None:
                        src_id = nid
                    if name == e["target_name"] and tgt_id is None:
                        tgt_id = nid
                if not src_id or not tgt_id:
                    parse.errors.append(
                        f"Sheet 边 (类型 {code}): 源节点 '{e['source_name']}' 或 目标节点 "
                        f"'{e['target_name']}' 未找到"
                    )
                    continue
                eid = f"edge_{uuid.uuid4().hex[:12]}"
                conn.execute(
                    "INSERT INTO edges (id, topology_id, edge_type_id, source_id, target_id, status) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (eid, topology_id, et["id"], src_id, tgt_id, e.get("status") or "online"),
                )
                for k, v in (e.get("attrs") or {}).items():
                    conn.execute(
                        "INSERT INTO edge_attrs (edge_id, field_key, value) VALUES (?, ?, ?)",
                        (eid, k, str(v) if v is not None else None),
                    )

        group_id_by_name = {}
        for g in parse.node_groups:
            nt = conn.execute(
                "SELECT id FROM node_types WHERE code = ?", (g.get("node_type_code"),)
            ).fetchone()
            if not nt:
                parse.errors.append(f"节点组 '{g['group_name']}': 节点类型代码 "
                                    f"'{g.get('node_type_code')}' 不存在")
                continue
            gid = f"grp_{uuid.uuid4().hex[:12]}"
            conn.execute(
                "INSERT INTO node_groups (id, topology_id, node_type_id, group_name, "
                "node_count, name_template, attr_strategies, canvas_x, canvas_y) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (gid, topology_id, nt["id"], g["group_name"],
                 int(g.get("node_count") or 1),
                 g.get("name_template") or "{group}-{i:05d}",
                 json.dumps(g.get("attr_strategies") or [], ensure_ascii=False),
                 g.get("canvas_x"), g.get("canvas_y")),
            )
            group_id_by_name[g["group_name"]] = gid

        strategies_by_group: dict = {}
        for s in parse.node_group_edge_strategies:
            src_gid = group_id_by_name.get(s["source_group_name"])
            if not src_gid:
                parse.errors.append(f"节点组边策略: 源组 '{s['source_group_name']}' 未找到")
                continue
            if s["target_kind"] == "组":
                target_id = group_id_by_name.get(s["target_name"])
                if not target_id:
                    parse.errors.append(f"节点组边策略: 目标组 '{s['target_name']}' 未找到")
                    continue
            else:
                target_id = None
                for (c, name), nid in node_id_by_name_type.items():
                    if name == s["target_name"]:
                        target_id = nid
                        break
                if not target_id:
                    parse.errors.append(f"节点组边策略: 目标节点 '{s['target_name']}' 未找到")
                    continue
            strategies_by_group.setdefault(src_gid, []).append({
                "target_group_id": target_id,
                "edge_type_code": s["edge_type_code"],
                "mode": s["mode"],
                "ratio_k": s.get("ratio_k"),
            })
        for gid, strategies in strategies_by_group.items():
            conn.execute(
                "UPDATE node_groups SET edge_strategies = ? WHERE id = ?",
                (json.dumps(strategies, ensure_ascii=False), gid),
            )

        alarm_count_by_node = 0
        for a in parse.node_alarms:
            code = a.get("node_type_code")
            name = a.get("node_name")
            nid = node_id_by_name_type.get((code, name))
            if not nid:
                parse.errors.append(f"节点告警: 节点 ({code}, {name}) 未找到")
                continue
            aid = f"alm_{uuid.uuid4().hex[:12]}"
            conn.execute(
                "INSERT INTO node_alarms (id, node_id, alarm_index) VALUES (?, ?, ?)",
                (aid, nid, int(a.get("alarm_index") or 1)),
            )
            alarm_count_by_node += 1
            for k, v in (a.get("attrs") or {}).items():
                conn.execute(
                    "INSERT INTO node_alarm_attrs (alarm_id, field_key, value) VALUES (?, ?, ?)",
                    (aid, k, str(v) if v is not None else None),
                )

        group_alarm_count = 0
        for a in parse.node_group_alarms:
            gid = group_id_by_name.get(a.get("group_name"))
            if not gid:
                parse.errors.append(f"节点组告警: 组 '{a.get('group_name')}' 未找到")
                continue
            aid = f"grp_alm_{uuid.uuid4().hex[:12]}"
            conn.execute(
                "INSERT INTO node_group_alarms (id, node_group_id, alarm_index) VALUES (?, ?, ?)",
                (aid, gid, int(a.get("alarm_index") or 1)),
            )
            group_alarm_count += 1
            for k, v in (a.get("attrs") or {}).items():
                conn.execute(
                    "INSERT INTO node_group_alarm_attrs (alarm_id, field_key, value) VALUES (?, ?, ?)",
                    (aid, k, str(v) if v is not None else None),
                )

    total_nodes = sum(len(v) for v in parse.nodes_by_type_code.values())
    total_edges = sum(len(v) for v in parse.edges_by_type_code.values())

    return {
        "code": 0,
        "data": {
            "topologyId": topology_id,
            "topologyName": new_name,
            "counts": {
                "nodes": total_nodes,
                "edges": total_edges,
                "groups": len(parse.node_groups),
                "nodeAlarms": alarm_count_by_node,
                "groupAlarms": group_alarm_count,
            },
            "errors": parse.errors,
            "warnings": parse.warnings,
        },
        "message": "ok",
    }
