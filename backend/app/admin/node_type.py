import uuid
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from app.db.connection import connect, transaction
from app.admin.schemas.node_type import (
    NodeTypeCreate,
    NodeTypeUpdate,
    NodeTypeDetail,
    NodeTypeItem,
    NodeTypeFieldItem,
    NodeTypeFieldCreate,
    NodeTypeFieldUpdate,
    NodeTypeBatchDelete,
    EdgeTypeBatchDelete,
    TypeExportRequest,
    EdgeTypeCreate,
    EdgeTypeUpdate,
    EdgeTypeDetail,
    EdgeTypeItem,
    EdgeTypeFieldItem,
    EdgeTypeFieldCreate,
    EdgeTypeFieldUpdate,
)

router = APIRouter(prefix="/admin/api", tags=["类型"])


def _new_id() -> str:
    return f"ntype_{uuid.uuid4().hex[:12]}"


def _new_edge_id() -> str:
    return f"etype_{uuid.uuid4().hex[:12]}"


def _row_to_node_type_item(row) -> NodeTypeItem:
    return NodeTypeItem(
        id=row["id"],
        code=row["code"],
        name=row["name"],
        category=row["category"],
        icon=row["icon"],
        color=row["color"],
        shape=row["shape"],
        render_mode=row["render_mode"],
        dn_template=row["dn_template"],
        description=row["description"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _row_to_edge_type_item(row) -> EdgeTypeItem:
    return EdgeTypeItem(
        id=row["id"],
        code=row["code"],
        name=row["name"],
        semantic=row["semantic"],
        directed=bool(row["directed"]),
        exclusive_target=bool(row["exclusive_target"]),
        allow_source_type_codes=row["allow_source_type_codes"],
        allow_target_type_codes=row["allow_target_type_codes"],
        line_style=row["line_style"],
        color=row["color"],
        description=row["description"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _get_node_type_fields(conn, node_type_id: str) -> list[NodeTypeFieldItem]:
    rows = conn.execute(
        "SELECT * FROM node_type_fields WHERE node_type_id = ? ORDER BY sort_order",
        (node_type_id,),
    ).fetchall()
    return [
        NodeTypeFieldItem(
            id=r["id"],
            node_type_id=r["node_type_id"],
            field_key=r["field_key"],
            field_label=r["field_label"],
            field_type=r["field_type"],
            max_length=r["max_length"],
            default_value=r["default_value"],
            options=r["options"],
            required=bool(r["required"]),
            sort_order=r["sort_order"],
        )
        for r in rows
    ]


def _get_edge_type_fields(conn, edge_type_id: str) -> list[EdgeTypeFieldItem]:
    rows = conn.execute(
        "SELECT * FROM edge_type_fields WHERE edge_type_id = ? ORDER BY sort_order",
        (edge_type_id,),
    ).fetchall()
    return [
        EdgeTypeFieldItem(
            id=r["id"],
            edge_type_id=r["edge_type_id"],
            field_key=r["field_key"],
            field_label=r["field_label"],
            field_type=r["field_type"],
            max_length=r["max_length"],
            default_value=r["default_value"],
            options=r["options"],
            required=bool(r["required"]),
            sort_order=r["sort_order"],
        )
        for r in rows
    ]


# ============== node_types ==============

@router.get("/node-types")
def list_node_types() -> dict:
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM node_types ORDER BY category, name"
        ).fetchall()
        items = []
        for r in rows:
            item = NodeTypeDetail(
                id=r["id"],
                code=r["code"],
                name=r["name"],
                category=r["category"],
                icon=r["icon"],
                color=r["color"],
                shape=r["shape"],
                render_mode=r["render_mode"],
                dn_template=r["dn_template"],
                description=r["description"],
                created_at=r["created_at"],
                updated_at=r["updated_at"],
                fields=_get_node_type_fields(conn, r["id"]),
            )
            items.append(item.model_dump(mode="json", by_alias=True))
        return {"code": 0, "data": {"items": items, "total": len(items)}, "message": "ok"}


@router.get("/node-types/{type_id}")
def get_node_type(type_id: str) -> dict:
    with connect() as conn:
        row = conn.execute(
            "SELECT * FROM node_types WHERE id = ?", (type_id,)
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail={"code": 40201, "message": "类型不存在"})
        item = NodeTypeDetail(
            id=row["id"],
            code=row["code"],
            name=row["name"],
            category=row["category"],
            icon=row["icon"],
            color=row["color"],
            shape=row["shape"],
            render_mode=row["render_mode"],
            dn_template=row["dn_template"],
            description=row["description"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            fields=_get_node_type_fields(conn, row["id"]),
        )
        return {"code": 0, "data": item.model_dump(mode="json", by_alias=True), "message": "ok"}


@router.post("/node-types")
def create_node_type(data: NodeTypeCreate) -> dict:
    type_id = _new_id()
    with transaction() as conn:
        existing = conn.execute(
            "SELECT id FROM node_types WHERE code = ?", (data.code,)
        ).fetchone()
        if existing:
            raise HTTPException(status_code=409, detail={"code": 40202, "message": "类型代码已存在"})
        conn.execute(
            """INSERT INTO node_types (id, code, name, category, icon, color, shape, render_mode, dn_template, description)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (type_id, data.code, data.name, data.category, data.icon, data.color,
             data.shape, data.render_mode, data.dn_template, data.description),
        )
    return {"code": 0, "data": {"id": type_id}, "message": "ok"}


@router.put("/node-types/{type_id}")
def update_node_type(type_id: str, data: NodeTypeUpdate) -> dict:
    fields = data.model_dump(exclude_unset=True)
    if not fields:
        raise HTTPException(status_code=400, detail={"code": 40203, "message": "无更新字段"})
    with transaction() as conn:
        existing = conn.execute(
            "SELECT id FROM node_types WHERE id = ?", (type_id,)
        ).fetchone()
        if not existing:
            raise HTTPException(status_code=404, detail={"code": 40201, "message": "类型不存在"})
        set_clause = ", ".join(f"{k} = ?" for k in fields.keys())
        conn.execute(
            f"UPDATE node_types SET {set_clause}, updated_at = datetime('now') WHERE id = ?",
            (*fields.values(), type_id),
        )
    return {"code": 0, "data": {"id": type_id}, "message": "ok"}


@router.post("/node-types/batch-delete")
def batch_delete_node_types(data: NodeTypeBatchDelete) -> dict:
    deleted_count = 0
    skipped: list[dict] = []
    with transaction() as conn:
        for type_id in data.ids:
            existing = conn.execute(
                "SELECT id FROM node_types WHERE id = ?", (type_id,)
            ).fetchone()
            if not existing:
                skipped.append({"id": type_id, "reason": "类型不存在"})
                continue
            in_use = conn.execute(
                "SELECT id FROM nodes WHERE node_type_id = ? LIMIT 1", (type_id,)
            ).fetchone()
            if in_use:
                skipped.append({"id": type_id, "reason": "该类型已被节点使用，无法删除"})
                continue
            conn.execute("DELETE FROM node_type_fields WHERE node_type_id = ?", (type_id,))
            conn.execute("DELETE FROM node_types WHERE id = ?", (type_id,))
            deleted_count += 1
    return {"code": 0, "data": {"deletedCount": deleted_count, "skipped": skipped}, "message": "ok"}


@router.post("/node-types/export")
def export_node_types(data: TypeExportRequest) -> dict:
    with connect() as conn:
        if data.ids:
            placeholders = ",".join("?" for _ in data.ids)
            rows = conn.execute(
                f"SELECT * FROM node_types WHERE id IN ({placeholders}) ORDER BY category, name",
                tuple(data.ids),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM node_types ORDER BY category, name"
            ).fetchall()
        items = []
        for r in rows:
            item = NodeTypeDetail(
                id=r["id"],
                code=r["code"],
                name=r["name"],
                category=r["category"],
                icon=r["icon"],
                color=r["color"],
                shape=r["shape"],
                render_mode=r["render_mode"],
                dn_template=r["dn_template"],
                description=r["description"],
                created_at=r["created_at"],
                updated_at=r["updated_at"],
                fields=_get_node_type_fields(conn, r["id"]),
            )
            items.append(item.model_dump(mode="json", by_alias=True))
        return {"code": 0, "data": {"items": items}, "message": "ok"}


@router.delete("/node-types/{type_id}")
def delete_node_type(type_id: str) -> dict:
    with transaction() as conn:
        existing = conn.execute(
            "SELECT id FROM node_types WHERE id = ?", (type_id,)
        ).fetchone()
        if not existing:
            raise HTTPException(status_code=404, detail={"code": 40201, "message": "类型不存在"})
        in_use = conn.execute(
            "SELECT id FROM nodes WHERE node_type_id = ? LIMIT 1", (type_id,)
        ).fetchone()
        if in_use:
            raise HTTPException(status_code=409, detail={"code": 40201, "message": "该类型已被节点使用，无法删除"})
        conn.execute("DELETE FROM node_types WHERE id = ?", (type_id,))
    return {"code": 0, "data": {"id": type_id}, "message": "ok"}


# ============== node_type_fields ==============

@router.post("/node-types/{type_id}/fields")
def create_node_type_field(type_id: str, data: NodeTypeFieldCreate) -> dict:
    with transaction() as conn:
        existing = conn.execute(
            "SELECT id FROM node_types WHERE id = ?", (type_id,)
        ).fetchone()
        if not existing:
            raise HTTPException(status_code=404, detail={"code": 40201, "message": "类型不存在"})
        key_exists = conn.execute(
            "SELECT id FROM node_type_fields WHERE node_type_id = ? AND field_key = ?",
            (type_id, data.field_key),
        ).fetchone()
        if key_exists:
            raise HTTPException(status_code=409, detail={"code": 40204, "message": "字段Key已存在"})
        conn.execute(
            """INSERT INTO node_type_fields
               (node_type_id, field_key, field_label, field_type, max_length, default_value, options, required, sort_order)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (type_id, data.field_key, data.field_label, data.field_type,
             data.max_length, data.default_value, data.options, int(data.required), data.sort_order),
        )
        row = conn.execute(
            "SELECT last_insert_rowid() as id"
        ).fetchone()
    return {"code": 0, "data": {"id": row["id"]}, "message": "ok"}


@router.put("/node-types/{type_id}/fields/{field_id}")
def update_node_type_field(type_id: str, field_id: int, data: NodeTypeFieldUpdate) -> dict:
    fields = data.model_dump(exclude_unset=True)
    if not fields:
        raise HTTPException(status_code=400, detail={"code": 40203, "message": "无更新字段"})
    with transaction() as conn:
        existing = conn.execute(
            "SELECT id FROM node_type_fields WHERE id = ? AND node_type_id = ?",
            (field_id, type_id),
        ).fetchone()
        if not existing:
            raise HTTPException(status_code=404, detail={"code": 40205, "message": "字段不存在"})
        set_clause = ", ".join(f"{k} = ?" for k in fields.keys())
        if "required" in fields:
            fields["required"] = int(fields["required"])
        conn.execute(
            f"UPDATE node_type_fields SET {set_clause} WHERE id = ?",
            (*fields.values(), field_id),
        )
    return {"code": 0, "data": {"id": field_id}, "message": "ok"}


@router.delete("/node-types/{type_id}/fields/{field_id}")
def delete_node_type_field(type_id: str, field_id: int) -> dict:
    with transaction() as conn:
        existing = conn.execute(
            "SELECT id FROM node_type_fields WHERE id = ? AND node_type_id = ?",
            (field_id, type_id),
        ).fetchone()
        if not existing:
            raise HTTPException(status_code=404, detail={"code": 40205, "message": "字段不存在"})
        conn.execute("DELETE FROM node_type_fields WHERE id = ?", (field_id,))
    return {"code": 0, "data": {"id": field_id}, "message": "ok"}


# ============== edge_types ==============

@router.get("/edge-types")
def list_edge_types() -> dict:
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM edge_types ORDER BY name"
        ).fetchall()
        items = []
        for r in rows:
            item = EdgeTypeDetail(
                id=r["id"],
                code=r["code"],
                name=r["name"],
                semantic=r["semantic"],
                directed=bool(r["directed"]),
                exclusive_target=bool(r["exclusive_target"]),
                allow_source_type_codes=r["allow_source_type_codes"],
                allow_target_type_codes=r["allow_target_type_codes"],
                line_style=r["line_style"],
                color=r["color"],
                description=r["description"],
                created_at=r["created_at"],
                updated_at=r["updated_at"],
                fields=_get_edge_type_fields(conn, r["id"]),
            )
            items.append(item.model_dump(mode="json", by_alias=True))
        return {"code": 0, "data": {"items": items, "total": len(items)}, "message": "ok"}


@router.get("/edge-types/{type_id}")
def get_edge_type(type_id: str) -> dict:
    with connect() as conn:
        row = conn.execute(
            "SELECT * FROM edge_types WHERE id = ?", (type_id,)
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail={"code": 40301, "message": "类型不存在"})
        item = EdgeTypeDetail(
            id=row["id"],
            code=row["code"],
            name=row["name"],
            semantic=row["semantic"],
            directed=bool(row["directed"]),
            exclusive_target=bool(row["exclusive_target"]),
            allow_source_type_codes=row["allow_source_type_codes"],
            allow_target_type_codes=row["allow_target_type_codes"],
            line_style=row["line_style"],
            color=row["color"],
            description=row["description"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            fields=_get_edge_type_fields(conn, row["id"]),
        )
        return {"code": 0, "data": item.model_dump(mode="json", by_alias=True), "message": "ok"}


@router.post("/edge-types")
def create_edge_type(data: EdgeTypeCreate) -> dict:
    type_id = _new_edge_id()
    with transaction() as conn:
        existing = conn.execute(
            "SELECT id FROM edge_types WHERE code = ?", (data.code,)
        ).fetchone()
        if existing:
            raise HTTPException(status_code=409, detail={"code": 40302, "message": "类型代码已存在"})
        conn.execute(
            """INSERT INTO edge_types
               (id, code, name, semantic, directed, exclusive_target,
                allow_source_type_codes, allow_target_type_codes, line_style, color, description)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (type_id, data.code, data.name, data.semantic, int(data.directed),
             int(data.exclusive_target), data.allow_source_type_codes,
             data.allow_target_type_codes, data.line_style, data.color, data.description),
        )
    return {"code": 0, "data": {"id": type_id}, "message": "ok"}


@router.put("/edge-types/{type_id}")
def update_edge_type(type_id: str, data: EdgeTypeUpdate) -> dict:
    fields = data.model_dump(exclude_unset=True)
    if not fields:
        raise HTTPException(status_code=400, detail={"code": 40303, "message": "无更新字段"})
    with transaction() as conn:
        existing = conn.execute(
            "SELECT id FROM edge_types WHERE id = ?", (type_id,)
        ).fetchone()
        if not existing:
            raise HTTPException(status_code=404, detail={"code": 40301, "message": "类型不存在"})
        set_clause = ", ".join(f"{k} = ?" for k in fields.keys())
        conn.execute(
            f"UPDATE edge_types SET {set_clause}, updated_at = datetime('now') WHERE id = ?",
            (*fields.values(), type_id),
        )
    return {"code": 0, "data": {"id": type_id}, "message": "ok"}


@router.post("/edge-types/batch-delete")
def batch_delete_edge_types(data: EdgeTypeBatchDelete) -> dict:
    deleted_count = 0
    skipped: list[dict] = []
    with transaction() as conn:
        for type_id in data.ids:
            existing = conn.execute(
                "SELECT id FROM edge_types WHERE id = ?", (type_id,)
            ).fetchone()
            if not existing:
                skipped.append({"id": type_id, "reason": "类型不存在"})
                continue
            in_use = conn.execute(
                "SELECT id FROM edges WHERE edge_type_id = ? LIMIT 1", (type_id,)
            ).fetchone()
            if in_use:
                skipped.append({"id": type_id, "reason": "该类型已被边使用，无法删除"})
                continue
            conn.execute("DELETE FROM edge_type_fields WHERE edge_type_id = ?", (type_id,))
            conn.execute("DELETE FROM edge_types WHERE id = ?", (type_id,))
            deleted_count += 1
    return {"code": 0, "data": {"deletedCount": deleted_count, "skipped": skipped}, "message": "ok"}


@router.post("/edge-types/export")
def export_edge_types(data: TypeExportRequest) -> dict:
    with connect() as conn:
        if data.ids:
            placeholders = ",".join("?" for _ in data.ids)
            rows = conn.execute(
                f"SELECT * FROM edge_types WHERE id IN ({placeholders}) ORDER BY name",
                tuple(data.ids),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM edge_types ORDER BY name"
            ).fetchall()
        items = []
        for r in rows:
            item = EdgeTypeDetail(
                id=r["id"],
                code=r["code"],
                name=r["name"],
                semantic=r["semantic"],
                directed=bool(r["directed"]),
                exclusive_target=bool(r["exclusive_target"]),
                allow_source_type_codes=r["allow_source_type_codes"],
                allow_target_type_codes=r["allow_target_type_codes"],
                line_style=r["line_style"],
                color=r["color"],
                description=r["description"],
                created_at=r["created_at"],
                updated_at=r["updated_at"],
                fields=_get_edge_type_fields(conn, r["id"]),
            )
            items.append(item.model_dump(mode="json", by_alias=True))
        return {"code": 0, "data": {"items": items}, "message": "ok"}


@router.delete("/edge-types/{type_id}")
def delete_edge_type(type_id: str) -> dict:
    with transaction() as conn:
        existing = conn.execute(
            "SELECT id FROM edge_types WHERE id = ?", (type_id,)
        ).fetchone()
        if not existing:
            raise HTTPException(status_code=404, detail={"code": 40301, "message": "类型不存在"})
        in_use = conn.execute(
            "SELECT id FROM edges WHERE edge_type_id = ? LIMIT 1", (type_id,)
        ).fetchone()
        if in_use:
            raise HTTPException(status_code=409, detail={"code": 40301, "message": "该类型已被边使用，无法删除"})
        conn.execute("DELETE FROM edge_types WHERE id = ?", (type_id,))
    return {"code": 0, "data": {"id": type_id}, "message": "ok"}


# ============== edge_type_fields ==============

@router.post("/edge-types/{type_id}/fields")
def create_edge_type_field(type_id: str, data: EdgeTypeFieldCreate) -> dict:
    with transaction() as conn:
        existing = conn.execute(
            "SELECT id FROM edge_types WHERE id = ?", (type_id,)
        ).fetchone()
        if not existing:
            raise HTTPException(status_code=404, detail={"code": 40301, "message": "类型不存在"})
        key_exists = conn.execute(
            "SELECT id FROM edge_type_fields WHERE edge_type_id = ? AND field_key = ?",
            (type_id, data.field_key),
        ).fetchone()
        if key_exists:
            raise HTTPException(status_code=409, detail={"code": 40304, "message": "字段Key已存在"})
        conn.execute(
            """INSERT INTO edge_type_fields
               (edge_type_id, field_key, field_label, field_type, max_length, default_value, options, required, sort_order)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (type_id, data.field_key, data.field_label, data.field_type,
             data.max_length, data.default_value, data.options, int(data.required), data.sort_order),
        )
        row = conn.execute(
            "SELECT last_insert_rowid() as id"
        ).fetchone()
    return {"code": 0, "data": {"id": row["id"]}, "message": "ok"}


@router.put("/edge-types/{type_id}/fields/{field_id}")
def update_edge_type_field(type_id: str, field_id: int, data: EdgeTypeFieldUpdate) -> dict:
    fields = data.model_dump(exclude_unset=True)
    if not fields:
        raise HTTPException(status_code=400, detail={"code": 40303, "message": "无更新字段"})
    with transaction() as conn:
        existing = conn.execute(
            "SELECT id FROM edge_type_fields WHERE id = ? AND edge_type_id = ?",
            (field_id, type_id),
        ).fetchone()
        if not existing:
            raise HTTPException(status_code=404, detail={"code": 40305, "message": "字段不存在"})
        set_clause = ", ".join(f"{k} = ?" for k in fields.keys())
        if "required" in fields:
            fields["required"] = int(fields["required"])
        conn.execute(
            f"UPDATE edge_type_fields SET {set_clause} WHERE id = ?",
            (*fields.values(), field_id),
        )
    return {"code": 0, "data": {"id": field_id}, "message": "ok"}


@router.delete("/edge-types/{type_id}/fields/{field_id}")
def delete_edge_type_field(type_id: str, field_id: int) -> dict:
    with transaction() as conn:
        existing = conn.execute(
            "SELECT id FROM edge_type_fields WHERE id = ? AND edge_type_id = ?",
            (field_id, type_id),
        ).fetchone()
        if not existing:
            raise HTTPException(status_code=404, detail={"code": 40305, "message": "字段不存在"})
        conn.execute("DELETE FROM edge_type_fields WHERE id = ?", (field_id,))
    return {"code": 0, "data": {"id": field_id}, "message": "ok"}
