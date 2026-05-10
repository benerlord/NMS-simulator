import uuid
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from app.db.connection import connect, transaction
from app.admin.schemas.edge import (
    EdgeCreate,
    EdgeUpdate,
    EdgeDetail,
    EdgeItem,
    EdgeAttrSet,
)

router = APIRouter(prefix="/admin/api", tags=["边"])


def _new_id() -> str:
    return f"edge_{uuid.uuid4().hex[:12]}"


def _row_to_edge_item(row) -> EdgeItem:
    return EdgeItem(
        id=row["id"],
        topology_id=row["topology_id"],
        edge_type_id=row["edge_type_id"],
        source_id=row["source_id"],
        target_id=row["target_id"],
        status=row["status"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _get_required_edge_fields(conn, edge_type_id: str) -> set[str]:
    rows = conn.execute(
        "SELECT field_key FROM edge_type_fields WHERE edge_type_id = ? AND required = 1",
        (edge_type_id,),
    ).fetchall()
    return {r["field_key"] for r in rows}


def _get_max_length_edge_map(conn, edge_type_id: str) -> dict[str, tuple[str, int]]:
    """返回 {field_key: (field_label, max_length)} 仅包含定义了 max_length 的文本字段"""
    rows = conn.execute(
        "SELECT field_key, field_label, max_length FROM edge_type_fields "
        "WHERE edge_type_id = ? AND field_type = 'text' AND max_length IS NOT NULL",
        (edge_type_id,),
    ).fetchall()
    return {r["field_key"]: (r["field_label"], r["max_length"]) for r in rows}


def _get_edge_attrs(conn, edge_id: str) -> dict:
    rows = conn.execute(
        "SELECT field_key, value FROM edge_attrs WHERE edge_id = ?", (edge_id,)
    ).fetchall()
    return {r["field_key"]: r["value"] for r in rows}


def _build_edge_detail(conn, row) -> EdgeDetail:
    attrs = _get_edge_attrs(conn, row["id"])
    return EdgeDetail(
        id=row["id"],
        topology_id=row["topology_id"],
        edge_type_id=row["edge_type_id"],
        source_id=row["source_id"],
        target_id=row["target_id"],
        status=row["status"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        attrs=attrs,
    )


# GET /admin/api/topologies/{topologyId}/edges
@router.get("/topologies/{topology_id}/edges")
def list_edges(
    topology_id: str,
    edge_type_id: Optional[str] = Query(None, description="边类型ID过滤"),
    source_id: Optional[str] = Query(None, description="源节点ID过滤"),
    target_id: Optional[str] = Query(None, description="目标节点ID过滤"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
) -> dict:
    with connect() as conn:
        topo = conn.execute(
            "SELECT id FROM topologies WHERE id = ?", (topology_id,)
        ).fetchone()
        if not topo:
            raise HTTPException(
                status_code=404,
                detail={"code": 40101, "message": "拓扑不存在"},
            )

    conditions = ["topology_id = ?"]
    params = [topology_id]
    if edge_type_id:
        conditions.append("edge_type_id = ?")
        params.append(edge_type_id)
    if source_id:
        conditions.append("source_id = ?")
        params.append(source_id)
    if target_id:
        conditions.append("target_id = ?")
        params.append(target_id)

    where = "WHERE " + " AND ".join(conditions)

    with connect() as conn:
        total = conn.execute(
            f"SELECT COUNT(*) FROM edges {where}", params
        ).fetchone()[0]
        offset = (page - 1) * page_size
        rows = conn.execute(
            f"""
            SELECT * FROM edges {where}
            ORDER BY updated_at DESC
            LIMIT ? OFFSET ?
            """,
            params + [page_size, offset],
        ).fetchall()

    items = [_row_to_edge_item(r) for r in rows]
    return {
        "code": 0,
        "data": {
            "items": [m.model_dump(mode="json", by_alias=True) for m in items],
            "total": total,
            "page": page,
            "pageSize": page_size,
        },
        "message": "ok",
    }


# GET /admin/api/edges/{edge_id}
@router.get("/edges/{edge_id}")
def get_edge(edge_id: str) -> dict:
    with connect() as conn:
        row = conn.execute(
            "SELECT * FROM edges WHERE id = ?", (edge_id,)
        ).fetchone()
        if not row:
            raise HTTPException(
                status_code=404,
                detail={"code": 40106, "message": "边不存在"},
            )
        detail = _build_edge_detail(conn, row)
    return {"code": 0, "data": detail.model_dump(mode="json", by_alias=True), "message": "ok"}


# POST /admin/api/topologies/{topology_id}/edges
@router.post("/topologies/{topology_id}/edges")
def create_edge(topology_id: str, data: EdgeCreate) -> dict:
    edge_id = _new_id()

    with transaction() as conn:
        # 检查拓扑存在
        topo = conn.execute(
            "SELECT id FROM topologies WHERE id = ?", (topology_id,)
        ).fetchone()
        if not topo:
            raise HTTPException(
                status_code=404,
                detail={"code": 40101, "message": "拓扑不存在"},
            )

        # 检查边类型存在
        edge_type = conn.execute(
            "SELECT id, exclusive_target, allow_source_type_codes, allow_target_type_codes FROM edge_types WHERE id = ?",
            (data.edge_type_id,)
        ).fetchone()
        if not edge_type:
            raise HTTPException(
                status_code=400,
                detail={"code": 40001, "message": "边类型不存在"},
            )

        # 检查源节点存在且在同一拓扑
        source = conn.execute(
            "SELECT id, topology_id, node_type_id FROM nodes WHERE id = ?",
            (data.source_id,)
        ).fetchone()
        if not source:
            raise HTTPException(
                status_code=404,
                detail={"code": 40102, "message": "源节点不存在"},
            )
        if source["topology_id"] != topology_id:
            raise HTTPException(
                status_code=400,
                detail={"code": 40107, "message": "源节点和目标节点不在同一拓扑"},
            )

        # 检查目标节点存在且在同一拓扑
        target = conn.execute(
            "SELECT id, topology_id, node_type_id FROM nodes WHERE id = ?",
            (data.target_id,)
        ).fetchone()
        if not target:
            raise HTTPException(
                status_code=404,
                detail={"code": 40106, "message": "目标节点不存在"},
            )
        if target["topology_id"] != topology_id:
            raise HTTPException(
                status_code=400,
                detail={"code": 40107, "message": "源节点和目标节点不在同一拓扑"},
            )

        # 检查节点类型是否在允许列表中
        if edge_type["allow_source_type_codes"]:
            import json
            allowed_sources = json.loads(edge_type["allow_source_type_codes"])
            source_type = conn.execute(
                "SELECT code FROM node_types WHERE id = ?", (source["node_type_id"],)
            ).fetchone()
            if source_type and source_type["code"] not in allowed_sources:
                raise HTTPException(
                    status_code=400,
                    detail={"code": 40109, "message": "源节点类型不在允许范围内"},
                )

        if edge_type["allow_target_type_codes"]:
            import json
            allowed_targets = json.loads(edge_type["allow_target_type_codes"])
            target_type = conn.execute(
                "SELECT code FROM node_types WHERE id = ?", (target["node_type_id"],)
            ).fetchone()
            if target_type and target_type["code"] not in allowed_targets:
                raise HTTPException(
                    status_code=400,
                    detail={"code": 40109, "message": "目标节点类型不在允许范围内"},
                )

        # 检查 exclusive_target 约束：同一目标节点只能有一条此类入边
        if edge_type["exclusive_target"]:
            existing = conn.execute(
                "SELECT id FROM edges WHERE edge_type_id = ? AND target_id = ?",
                (data.edge_type_id, data.target_id),
            ).fetchone()
            if existing:
                raise HTTPException(
                    status_code=409,
                    detail={"code": 40108, "message": "该目标节点已存在相同类型的边"},
                )

        conn.execute(
            """INSERT INTO edges (id, topology_id, edge_type_id, source_id, target_id, status)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (edge_id, topology_id, data.edge_type_id, data.source_id, data.target_id, data.status),
        )
        row = conn.execute("SELECT * FROM edges WHERE id = ?", (edge_id,)).fetchone()
        detail = _build_edge_detail(conn, row)

    return {"code": 0, "data": detail.model_dump(mode="json", by_alias=True), "message": "ok"}


# PUT /admin/api/edges/{edge_id}
@router.put("/edges/{edge_id}")
def update_edge(edge_id: str, data: EdgeUpdate) -> dict:
    fields = data.model_dump(exclude_unset=True)
    if not fields:
        raise HTTPException(
            status_code=400,
            detail={"code": 40001, "message": "无更新字段"},
        )

    with connect() as conn:
        existing = conn.execute(
            "SELECT * FROM edges WHERE id = ?", (edge_id,)
        ).fetchone()
        if not existing:
            raise HTTPException(
                status_code=404,
                detail={"code": 40106, "message": "边不存在"},
            )

    set_clause = ", ".join(f"{k} = ?" for k in fields.keys())
    with transaction() as conn:
        conn.execute(
            f"UPDATE edges SET {set_clause}, updated_at = datetime('now') WHERE id = ?",
            (*fields.values(), edge_id),
        )
        row = conn.execute("SELECT * FROM edges WHERE id = ?", (edge_id,)).fetchone()
        detail = _build_edge_detail(conn, row)

    return {"code": 0, "data": detail.model_dump(mode="json", by_alias=True), "message": "ok"}


# DELETE /admin/api/edges/{edge_id}
@router.delete("/edges/{edge_id}")
def delete_edge(edge_id: str) -> dict:
    with connect() as conn:
        existing = conn.execute(
            "SELECT id FROM edges WHERE id = ?", (edge_id,)
        ).fetchone()
        if not existing:
            raise HTTPException(
                status_code=404,
                detail={"code": 40106, "message": "边不存在"},
            )

    with transaction() as conn:
        # edge_attrs 会通过 CASCADE 自动删除
        conn.execute("DELETE FROM edges WHERE id = ?", (edge_id,))

    return {"code": 0, "data": {"id": edge_id}, "message": "删除成功"}


# PUT /admin/api/edges/{edge_id}/attrs
@router.put("/edges/{edge_id}/attrs")
def set_edge_attrs(edge_id: str, attrs: list[EdgeAttrSet]) -> dict:
    with connect() as conn:
        edge_row = conn.execute(
            "SELECT id, edge_type_id FROM edges WHERE id = ?", (edge_id,)
        ).fetchone()
        if not edge_row:
            raise HTTPException(
                status_code=404,
                detail={"code": 40106, "message": "边不存在"},
            )

        # 校验必填字段
        required_fields = _get_required_edge_fields(conn, edge_row["edge_type_id"])
        provided_keys = {attr.field_key for attr in attrs}
        missing_required = required_fields - provided_keys

        if missing_required:
            # 获取缺失字段的中文名
            field_rows = conn.execute(
                "SELECT field_key, field_label FROM edge_type_fields WHERE edge_type_id = ? AND field_key IN (%s)" % ",".join("?" * len(missing_required)),
                [edge_row["edge_type_id"]] + list(missing_required),
            ).fetchall()
            missing_labels = [r["field_label"] for r in field_rows]
            raise HTTPException(
                status_code=400,
                detail={"code": 40110, "message": "必填字段不能为空", "details": {"missing_fields": missing_labels}},
            )

        # 校验 max_length
        max_len_map = _get_max_length_edge_map(conn, edge_row["edge_type_id"])
        for attr in attrs:
            if attr.field_key in max_len_map and attr.value:
                label, limit = max_len_map[attr.field_key]
                if len(attr.value) > limit:
                    raise HTTPException(
                        status_code=400,
                        detail={
                            "code": 40111,
                            "message": f"字段「{label}」内容长度不能超过 {limit} 个字符",
                        },
                    )

        with transaction() as tx:
            # 删除现有 attrs
            tx.execute("DELETE FROM edge_attrs WHERE edge_id = ?", (edge_id,))
            # 插入新 attrs
            for attr in attrs:
                tx.execute(
                    "INSERT INTO edge_attrs (edge_id, field_key, value) VALUES (?, ?, ?)",
                    (edge_id, attr.field_key, attr.value),
                )

        updated = _get_edge_attrs(conn, edge_id)

    return {"code": 0, "data": {"id": edge_id, "attrs": updated}, "message": "更新成功"}
