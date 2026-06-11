import uuid
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from app.db.connection import connect, transaction
from app.admin._alarm_utils import build_alarm_attrs
from app.admin.schemas.node import (
    NodeCreate,
    NodeUpdate,
    NodeDetail,
    NodeItem,
    NodeListItem,
    NodePositionUpdate,
    NodeAttrSet,
)

router = APIRouter(prefix="/admin/api", tags=["节点"])


def _new_id() -> str:
    return f"node_{uuid.uuid4().hex[:12]}"


def _row_to_node_item(row) -> NodeItem:
    return NodeItem(
        id=row["id"],
        topology_id=row["topology_id"],
        node_type_id=row["node_type_id"],
        name=row["name"],
        dn=row["dn"],
        status=row["status"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _get_node_attrs(conn, node_id: str) -> dict:
    rows = conn.execute(
        "SELECT field_key, value FROM node_attrs WHERE node_id = ?", (node_id,)
    ).fetchall()
    return {r["field_key"]: r["value"] for r in rows}


def _get_required_fields(conn, node_type_id: str) -> set[str]:
    rows = conn.execute(
        "SELECT field_key FROM node_type_fields WHERE node_type_id = ? AND required = 1",
        (node_type_id,),
    ).fetchall()
    return {r["field_key"] for r in rows}


def _get_max_length_map(conn, node_type_id: str) -> dict[str, tuple[str, int]]:
    """返回 {field_key: (field_label, max_length)} 仅包含定义了 max_length 的文本字段"""
    rows = conn.execute(
        "SELECT field_key, field_label, max_length FROM node_type_fields "
        "WHERE node_type_id = ? AND field_type = 'text' AND max_length IS NOT NULL",
        (node_type_id,),
    ).fetchall()
    return {r["field_key"]: (r["field_label"], r["max_length"]) for r in rows}


def _get_node_canvas(conn, node_id: str) -> tuple[Optional[float], Optional[float]]:
    row = conn.execute(
        "SELECT x, y FROM canvas_nodes WHERE node_id = ?", (node_id,)
    ).fetchone()
    if row:
        return row["x"], row["y"]
    return None, None


def _build_node_list_item(conn, row) -> NodeListItem:
    attrs = _get_node_attrs(conn, row["id"])
    x, y = _get_node_canvas(conn, row["id"])
    return NodeListItem(
        id=row["id"],
        topology_id=row["topology_id"],
        node_type_id=row["node_type_id"],
        name=row["name"],
        dn=row["dn"],
        status=row["status"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        x=x,
        y=y,
    )


def _build_node_detail(conn, row) -> NodeDetail:
    attrs = _get_node_attrs(conn, row["id"])
    x, y = _get_node_canvas(conn, row["id"])
    return NodeDetail(
        id=row["id"],
        topology_id=row["topology_id"],
        node_type_id=row["node_type_id"],
        name=row["name"],
        dn=row["dn"],
        status=row["status"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        attrs=attrs,
        x=x,
        y=y,
    )


# GET /admin/api/topologies/{topology_id}/nodes
@router.get("/topologies/{topology_id}/nodes")
def list_nodes(
    topology_id: str,
    node_type_id: Optional[str] = Query(None, description="节点类型ID过滤"),
    status: Optional[str] = Query(None, description="状态过滤"),
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
    if node_type_id:
        conditions.append("node_type_id = ?")
        params.append(node_type_id)
    if status:
        conditions.append("status = ?")
        params.append(status)

    where = "WHERE " + " AND ".join(conditions)

    with connect() as conn:
        total = conn.execute(
            f"SELECT COUNT(*) FROM nodes {where}", params
        ).fetchone()[0]
        offset = (page - 1) * page_size
        rows = conn.execute(
            f"""
            SELECT * FROM nodes {where}
            ORDER BY updated_at DESC
            LIMIT ? OFFSET ?
            """,
            params + [page_size, offset],
        ).fetchall()

        items = [_build_node_list_item(conn, r) for r in rows]

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


# GET /admin/api/nodes/{node_id}
@router.get("/nodes/{node_id}")
def get_node(node_id: str) -> dict:
    with connect() as conn:
        row = conn.execute(
            "SELECT * FROM nodes WHERE id = ?", (node_id,)
        ).fetchone()
        if not row:
            raise HTTPException(
                status_code=404,
                detail={"code": 40401, "message": "节点不存在"},
            )
        detail = _build_node_detail(conn, row)
    return {"code": 0, "data": detail.model_dump(mode="json", by_alias=True), "message": "ok"}


# POST /admin/api/topologies/{topology_id}/nodes
@router.post("/topologies/{topology_id}/nodes")
def create_node(topology_id: str, data: NodeCreate) -> dict:
    node_id = _new_id()

    with transaction() as conn:
        # 检查拓扑存在，同时取 alarm_schema_id 供后续自动告警使用
        topo = conn.execute(
            "SELECT id, alarm_schema_id FROM topologies WHERE id = ?", (topology_id,)
        ).fetchone()
        if not topo:
            raise HTTPException(
                status_code=404,
                detail={"code": 40402, "message": "拓扑不存在"},
            )
        # 检查节点类型存在
        ntype = conn.execute(
            "SELECT id FROM node_types WHERE id = ?", (data.node_type_id,)
        ).fetchone()
        if not ntype:
            raise HTTPException(
                status_code=404,
                detail={"code": 40403, "message": "节点类型不存在"},
            )
        # 检查 dn 唯一性（同一拓扑内）
        if data.dn:
            dup = conn.execute(
                "SELECT id FROM nodes WHERE topology_id = ? AND dn = ?",
                (topology_id, data.dn),
            ).fetchone()
            if dup:
                raise HTTPException(
                    status_code=409,
                    detail={"code": 40404, "message": "该拓扑内 DN 已存在"},
                )

        conn.execute(
            """INSERT INTO nodes (id, topology_id, node_type_id, name, dn, status)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (node_id, topology_id, data.node_type_id, data.name, data.dn, data.status),
        )

        # Auto-insert 1 default alarm if topology has alarm_schema bound
        if topo["alarm_schema_id"]:
            sid = topo["alarm_schema_id"]
            fields = conn.execute(
                "SELECT field_key, mapping_target, default_value FROM alarm_schema_fields "
                "WHERE alarm_schema_id = ? ORDER BY sort_order, id",
                (sid,),
            ).fetchall()
            aid = f"alm_{uuid.uuid4().hex[:12]}"
            conn.execute(
                "INSERT INTO node_alarms (id, node_id, alarm_index) VALUES (?, ?, 1)",
                (aid, node_id),
            )
            attrs = build_alarm_attrs(conn, node_id, fields)
            for k, v in attrs.items():
                conn.execute(
                    "INSERT INTO node_alarm_attrs (alarm_id, field_key, value) VALUES (?, ?, ?)",
                    (aid, k, v),
                )

        row = conn.execute("SELECT * FROM nodes WHERE id = ?", (node_id,)).fetchone()
        detail = _build_node_detail(conn, row)

    return {"code": 0, "data": detail.model_dump(mode="json", by_alias=True), "message": "ok"}


# PUT /admin/api/nodes/{node_id}
@router.put("/nodes/{node_id}")
def update_node(node_id: str, data: NodeUpdate) -> dict:
    fields = data.model_dump(exclude_unset=True)
    if not fields:
        raise HTTPException(
            status_code=400,
            detail={"code": 40405, "message": "无更新字段"},
        )

    with connect() as conn:
        existing = conn.execute(
            "SELECT * FROM nodes WHERE id = ?", (node_id,)
        ).fetchone()
        if not existing:
            raise HTTPException(
                status_code=404,
                detail={"code": 40401, "message": "节点不存在"},
            )

        # 检查 dn 唯一性
        if "dn" in fields and fields["dn"]:
            dup = conn.execute(
                "SELECT id FROM nodes WHERE topology_id = ? AND dn = ? AND id != ?",
                (existing["topology_id"], fields["dn"], node_id),
            ).fetchone()
            if dup:
                raise HTTPException(
                    status_code=409,
                    detail={"code": 40404, "message": "该拓扑内 DN 已存在"},
                )

    set_clause = ", ".join(f"{k} = ?" for k in fields.keys())
    with transaction() as conn:
        conn.execute(
            f"UPDATE nodes SET {set_clause}, updated_at = datetime('now') WHERE id = ?",
            (*fields.values(), node_id),
        )
        row = conn.execute("SELECT * FROM nodes WHERE id = ?", (node_id,)).fetchone()
        detail = _build_node_detail(conn, row)

    return {"code": 0, "data": detail.model_dump(mode="json", by_alias=True), "message": "ok"}


# DELETE /admin/api/nodes/{node_id}
@router.delete("/nodes/{node_id}")
def delete_node(node_id: str) -> dict:
    with connect() as conn:
        existing = conn.execute(
            "SELECT id FROM nodes WHERE id = ?", (node_id,)
        ).fetchone()
        if not existing:
            raise HTTPException(
                status_code=404,
                detail={"code": 40401, "message": "节点不存在"},
            )

    with transaction() as conn:
        # node_attrs 和 canvas_nodes 会通过 CASCADE 自动删除
        conn.execute("DELETE FROM nodes WHERE id = ?", (node_id,))

    return {"code": 0, "data": {"id": node_id}, "message": "删除成功"}


# PATCH /admin/api/nodes/{node_id}/position
@router.patch("/nodes/{node_id}/position")
def update_node_position(node_id: str, data: NodePositionUpdate) -> dict:
    with connect() as conn:
        existing = conn.execute(
            "SELECT id, topology_id FROM nodes WHERE id = ?", (node_id,)
        ).fetchone()
        if not existing:
            raise HTTPException(
                status_code=404,
                detail={"code": 40401, "message": "节点不存在"},
            )

        conn.execute(
            """
            INSERT OR REPLACE INTO canvas_nodes (node_id, topology_id, x, y)
            VALUES (?, ?, ?, ?)
            """,
            (node_id, existing["topology_id"], data.x, data.y),
        )

    return {"code": 0, "data": {"id": node_id, "x": data.x, "y": data.y}, "message": "更新成功"}


# PUT /admin/api/nodes/{node_id}/attrs
@router.put("/nodes/{node_id}/attrs")
def set_node_attrs(node_id: str, attrs: list[NodeAttrSet]) -> dict:
    with connect() as conn:
        node_row = conn.execute(
            "SELECT id, node_type_id FROM nodes WHERE id = ?", (node_id,)
        ).fetchone()
        if not node_row:
            raise HTTPException(
                status_code=404,
                detail={"code": 40401, "message": "节点不存在"},
            )

        # 校验必填字段
        required_fields = _get_required_fields(conn, node_row["node_type_id"])
        provided_keys = {attr.field_key for attr in attrs}
        missing_required = required_fields - provided_keys

        if missing_required:
            # 获取缺失字段的中文名
            field_rows = conn.execute(
                "SELECT field_key, field_label FROM node_type_fields WHERE node_type_id = ? AND field_key IN (%s)" % ",".join("?" * len(missing_required)),
                [node_row["node_type_id"]] + list(missing_required),
            ).fetchall()
            missing_labels = [r["field_label"] for r in field_rows]
            raise HTTPException(
                status_code=400,
                detail={"code": 40406, "message": "必填字段不能为空", "details": {"missing_fields": missing_labels}},
            )

        # 校验 max_length
        max_len_map = _get_max_length_map(conn, node_row["node_type_id"])
        for attr in attrs:
            if attr.field_key in max_len_map and attr.value:
                label, limit = max_len_map[attr.field_key]
                if len(attr.value) > limit:
                    raise HTTPException(
                        status_code=400,
                        detail={
                            "code": 40407,
                            "message": f"字段「{label}」内容长度不能超过 {limit} 个字符",
                        },
                    )

        with transaction() as tx:
            # 删除现有 attrs
            tx.execute("DELETE FROM node_attrs WHERE node_id = ?", (node_id,))
            # 插入新 attrs
            for attr in attrs:
                tx.execute(
                    "INSERT INTO node_attrs (node_id, field_key, value) VALUES (?, ?, ?)",
                    (node_id, attr.field_key, attr.value),
                )

        updated = _get_node_attrs(conn, node_id)

    return {"code": 0, "data": {"id": node_id, "attrs": updated}, "message": "更新成功"}
