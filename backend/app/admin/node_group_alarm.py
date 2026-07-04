import uuid
from typing import Any

from fastapi import APIRouter, HTTPException

from app.db.connection import connect, transaction
from app.admin.schemas import (
    NodeGroupAlarmAttrSet,
    NodeGroupAlarmCreate,
    NodeGroupAlarmItem,
)

router = APIRouter(prefix="/admin/api", tags=["节点组告警"])


def _new_alarm_id() -> str:
    return f"grp_alm_{uuid.uuid4().hex[:12]}"


def _get_alarm_schema_for_group(conn, group_id: str):
    """Return (alarm_schema_id, [field rows]); (None, []) if topology has no schema."""
    row = conn.execute(
        "SELECT t.alarm_schema_id AS sid FROM node_groups g "
        "JOIN topologies t ON t.id = g.topology_id "
        "WHERE g.id = ?",
        (group_id,),
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
        "SELECT field_key, value FROM node_group_alarm_attrs WHERE alarm_id = ?",
        (alarm_id,),
    ).fetchall()
    return {r["field_key"]: r["value"] for r in rows}


def _row_to_item(conn, row) -> NodeGroupAlarmItem:
    return NodeGroupAlarmItem(
        id=row["id"],
        node_group_id=row["node_group_id"],
        alarm_index=row["alarm_index"],
        attrs=_load_attrs(conn, row["id"]),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _next_alarm_index(conn, group_id: str) -> int:
    row = conn.execute(
        "SELECT COALESCE(MAX(alarm_index), 0) + 1 AS n "
        "FROM node_group_alarms WHERE node_group_id = ?",
        (group_id,),
    ).fetchone()
    return int(row["n"])


def _validate_attr_lengths(fields, attrs: dict) -> None:
    field_map = {f["field_key"]: f for f in fields}
    for k, v in attrs.items():
        f = field_map.get(k)
        if not f:
            continue
        if f["field_type"] == "text" and f["max_length"] and v and len(str(v)) > f["max_length"]:
            raise HTTPException(
                status_code=400,
                detail={"code": 40001, "message": f"字段 {k} 超过最大长度 {f['max_length']}"},
            )


def _strip_mapping_target_fields(fields, attrs: dict) -> dict:
    """mapping_target 字段的值在 CTE 展开时从虚拟节点取，不该存到模板 attrs 里。"""
    mapped = {f["field_key"] for f in fields if f["mapping_target"]}
    return {k: v for k, v in attrs.items() if k not in mapped}


@router.get("/node-groups/{group_id}/alarms")
def list_group_alarms(group_id: str) -> dict:
    with connect() as conn:
        grp = conn.execute("SELECT id FROM node_groups WHERE id = ?", (group_id,)).fetchone()
        if not grp:
            raise HTTPException(status_code=404, detail={"code": 40404, "message": "节点组不存在"})
        rows = conn.execute(
            "SELECT * FROM node_group_alarms WHERE node_group_id = ? ORDER BY alarm_index",
            (group_id,),
        ).fetchall()
        items = [_row_to_item(conn, r).model_dump(mode="json", by_alias=True) for r in rows]
    return {"code": 0, "data": items, "message": "ok"}


@router.post("/node-groups/{group_id}/alarms")
def create_group_alarm(group_id: str, data: NodeGroupAlarmCreate) -> dict:
    with transaction() as conn:
        grp = conn.execute("SELECT id FROM node_groups WHERE id = ?", (group_id,)).fetchone()
        if not grp:
            raise HTTPException(status_code=404, detail={"code": 40404, "message": "节点组不存在"})

        sid, fields = _get_alarm_schema_for_group(conn, group_id)
        if not sid:
            raise HTTPException(
                status_code=409,
                detail={"code": 40901, "message": "本拓扑未配置告警模板"},
            )

        user = data.attrs or {}
        # 用 default 补齐，但 mapping_target 字段不入模板（跟 spec 一致）
        merged = {}
        for f in fields:
            key = f["field_key"]
            if key in user and user[key] is not None:
                merged[key] = user[key]
            elif f["default_value"] is not None:
                merged[key] = f["default_value"]
        merged = _strip_mapping_target_fields(fields, merged)
        _validate_attr_lengths(fields, merged)

        aid = _new_alarm_id()
        idx = _next_alarm_index(conn, group_id)
        conn.execute(
            "INSERT INTO node_group_alarms (id, node_group_id, alarm_index) VALUES (?, ?, ?)",
            (aid, group_id, idx),
        )
        for k, v in merged.items():
            conn.execute(
                "INSERT INTO node_group_alarm_attrs (alarm_id, field_key, value) VALUES (?, ?, ?)",
                (aid, k, v),
            )

        row = conn.execute("SELECT * FROM node_group_alarms WHERE id = ?", (aid,)).fetchone()
        item = _row_to_item(conn, row)
    return {"code": 0, "data": item.model_dump(mode="json", by_alias=True), "message": "ok"}


@router.put("/node-group-alarms/{alarm_id}/attrs")
def update_group_alarm_attrs(alarm_id: str, data: NodeGroupAlarmAttrSet) -> dict:
    with transaction() as conn:
        row = conn.execute("SELECT * FROM node_group_alarms WHERE id = ?", (alarm_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail={"code": 40404, "message": "告警不存在"})

        _, fields = _get_alarm_schema_for_group(conn, row["node_group_id"])
        attrs = _strip_mapping_target_fields(fields, data.attrs)
        _validate_attr_lengths(fields, attrs)

        for k, v in attrs.items():
            if v is None:
                conn.execute(
                    "DELETE FROM node_group_alarm_attrs WHERE alarm_id = ? AND field_key = ?",
                    (alarm_id, k),
                )
            else:
                conn.execute(
                    "INSERT INTO node_group_alarm_attrs (alarm_id, field_key, value) VALUES (?, ?, ?) "
                    "ON CONFLICT(alarm_id, field_key) DO UPDATE SET value = excluded.value",
                    (alarm_id, k, v),
                )
        conn.execute(
            "UPDATE node_group_alarms SET updated_at = datetime('now') WHERE id = ?",
            (alarm_id,),
        )

        row = conn.execute("SELECT * FROM node_group_alarms WHERE id = ?", (alarm_id,)).fetchone()
        item = _row_to_item(conn, row)
    return {"code": 0, "data": item.model_dump(mode="json", by_alias=True), "message": "ok"}


@router.delete("/node-group-alarms/{alarm_id}")
def delete_group_alarm(alarm_id: str) -> dict:
    with transaction() as conn:
        row = conn.execute("SELECT id FROM node_group_alarms WHERE id = ?", (alarm_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail={"code": 40404, "message": "告警不存在"})
        conn.execute("DELETE FROM node_group_alarms WHERE id = ?", (alarm_id,))
    return {"code": 0, "data": None, "message": "ok"}
