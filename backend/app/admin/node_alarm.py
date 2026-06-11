import uuid
from typing import Any

from fastapi import APIRouter, HTTPException

from app.db.connection import connect, transaction
from app.admin._alarm_utils import build_alarm_attrs
from app.admin.schemas import (
    NodeAlarmAttrSet,
    NodeAlarmCreate,
    NodeAlarmItem,
)

router = APIRouter(prefix="/admin/api", tags=["节点告警"])


def _new_alarm_id() -> str:
    return f"alm_{uuid.uuid4().hex[:12]}"


def _get_alarm_schema_for_node(conn, node_id: str):
    """Return (alarm_schema_id, [field rows]); (None, []) if topology has no schema."""
    row = conn.execute(
        "SELECT t.alarm_schema_id AS sid FROM nodes n "
        "JOIN topologies t ON t.id = n.topology_id "
        "WHERE n.id = ?",
        (node_id,),
    ).fetchone()
    if not row or not row["sid"]:
        return None, []
    fields = conn.execute(
        "SELECT field_key, field_type, max_length, default_value, required, mapping_target "
        "FROM alarm_schema_fields WHERE alarm_schema_id = ? ORDER BY sort_order, id",
        (row["sid"],),
    ).fetchall()
    return row["sid"], fields


def _load_attrs(conn, alarm_id: str) -> dict[str, Any]:
    rows = conn.execute(
        "SELECT field_key, value FROM node_alarm_attrs WHERE alarm_id = ?",
        (alarm_id,),
    ).fetchall()
    return {r["field_key"]: r["value"] for r in rows}


def _row_to_item(conn, row) -> NodeAlarmItem:
    return NodeAlarmItem(
        id=row["id"],
        node_id=row["node_id"],
        alarm_index=row["alarm_index"],
        attrs=_load_attrs(conn, row["id"]),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _next_alarm_index(conn, node_id: str) -> int:
    row = conn.execute(
        "SELECT COALESCE(MAX(alarm_index), 0) + 1 AS n FROM node_alarms WHERE node_id = ?",
        (node_id,),
    ).fetchone()
    return int(row["n"])


def _validate_attr_lengths(fields, attrs: dict) -> None:
    field_map = {f["field_key"]: f for f in fields}
    for k, v in attrs.items():
        f = field_map.get(k)
        if not f:
            # Unknown field_key passes through — stored as-is in node_alarm_attrs without schema validation.
            continue
        if f["field_type"] == "text" and f["max_length"] and v and len(str(v)) > f["max_length"]:
            raise HTTPException(
                status_code=400,
                detail={
                    "code": 40001,
                    "message": f"字段 {k} 超过最大长度 {f['max_length']}",
                },
            )


@router.get("/nodes/{node_id}/alarms")
def list_node_alarms(node_id: str) -> dict:
    with connect() as conn:
        node = conn.execute("SELECT id FROM nodes WHERE id = ?", (node_id,)).fetchone()
        if not node:
            raise HTTPException(status_code=404, detail={"code": 40404, "message": "节点不存在"})
        rows = conn.execute(
            "SELECT * FROM node_alarms WHERE node_id = ? ORDER BY alarm_index",
            (node_id,),
        ).fetchall()
        items = [_row_to_item(conn, r).model_dump(mode="json", by_alias=True) for r in rows]
    return {"code": 0, "data": items, "message": "ok"}


@router.post("/nodes/{node_id}/alarms")
def create_node_alarm(node_id: str, data: NodeAlarmCreate) -> dict:
    with transaction() as conn:
        node = conn.execute("SELECT id FROM nodes WHERE id = ?", (node_id,)).fetchone()
        if not node:
            raise HTTPException(status_code=404, detail={"code": 40404, "message": "节点不存在"})

        sid, fields = _get_alarm_schema_for_node(conn, node_id)
        if not sid:
            raise HTTPException(
                status_code=409,
                detail={"code": 40901, "message": "本拓扑未配置告警模板"},
            )

        merged = build_alarm_attrs(conn, node_id, fields, user_provided=data.attrs)
        _validate_attr_lengths(fields, merged)

        aid = _new_alarm_id()
        idx = _next_alarm_index(conn, node_id)
        conn.execute(
            "INSERT INTO node_alarms (id, node_id, alarm_index) VALUES (?, ?, ?)",
            (aid, node_id, idx),
        )
        for k, v in merged.items():
            conn.execute(
                "INSERT INTO node_alarm_attrs (alarm_id, field_key, value) VALUES (?, ?, ?)",
                (aid, k, v),
            )

        row = conn.execute("SELECT * FROM node_alarms WHERE id = ?", (aid,)).fetchone()
        item = _row_to_item(conn, row)
    return {"code": 0, "data": item.model_dump(mode="json", by_alias=True), "message": "ok"}


@router.put("/alarms/{alarm_id}/attrs")
def update_alarm_attrs(alarm_id: str, data: NodeAlarmAttrSet) -> dict:
    with transaction() as conn:
        row = conn.execute("SELECT * FROM node_alarms WHERE id = ?", (alarm_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail={"code": 40404, "message": "告警不存在"})

        _, fields = _get_alarm_schema_for_node(conn, row["node_id"])
        _validate_attr_lengths(fields, data.attrs)

        for k, v in data.attrs.items():
            if v is None:
                conn.execute(
                    "DELETE FROM node_alarm_attrs WHERE alarm_id = ? AND field_key = ?",
                    (alarm_id, k),
                )
            else:
                conn.execute(
                    "INSERT INTO node_alarm_attrs (alarm_id, field_key, value) VALUES (?, ?, ?) "
                    "ON CONFLICT(alarm_id, field_key) DO UPDATE SET value = excluded.value",
                    (alarm_id, k, v),
                )
        conn.execute(
            "UPDATE node_alarms SET updated_at = datetime('now') WHERE id = ?",
            (alarm_id,),
        )

        row = conn.execute("SELECT * FROM node_alarms WHERE id = ?", (alarm_id,)).fetchone()
        item = _row_to_item(conn, row)
    return {"code": 0, "data": item.model_dump(mode="json", by_alias=True), "message": "ok"}


@router.delete("/alarms/{alarm_id}")
def delete_alarm(alarm_id: str) -> dict:
    with transaction() as conn:
        row = conn.execute("SELECT id FROM node_alarms WHERE id = ?", (alarm_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail={"code": 40404, "message": "告警不存在"})
        conn.execute("DELETE FROM node_alarms WHERE id = ?", (alarm_id,))
    return {"code": 0, "data": None, "message": "ok"}
