import uuid
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request

from app.db.connection import connect, transaction
from app.admin.schemas.mock_instance import (
    MockInstanceCreate,
    MockInstanceUpdate,
    MockInstanceItem,
    RequestLogItem,
)

router = APIRouter(prefix="/admin/api", tags=["实例"])


def _new_id() -> str:
    return f"inst_{uuid.uuid4().hex[:12]}"


def _get_runner(request: Request):
    return request.app.state.instance_runner


@router.get("/mock-instances")
def list_mock_instances() -> dict:
    with connect() as conn:
        rows = conn.execute("""
            SELECT m.*, t.name AS topology_name,
                   (SELECT COUNT(*) FROM api_configs a WHERE a.topology_id = m.topology_id) AS api_count
            FROM mock_instances m
            LEFT JOIN topologies t ON t.id = m.topology_id
            ORDER BY m.name
        """).fetchall()
        items = [
            MockInstanceItem(
                id=r["id"],
                name=r["name"],
                topology_id=r["topology_id"],
                topology_name=r["topology_name"],
                port=r["port"],
                description=r["description"],
                enabled=bool(r["enabled"]),
                api_count=r["api_count"],
                created_at=r["created_at"],
                updated_at=r["updated_at"],
            ).model_dump(mode="json", by_alias=True)
            for r in rows
        ]
    return {"code": 0, "data": {"items": items, "total": len(items)}, "message": "ok"}


@router.post("/mock-instances")
def create_mock_instance(data: MockInstanceCreate, request: Request) -> dict:
    with transaction() as conn:
        dup = conn.execute(
            "SELECT id, name FROM mock_instances WHERE port = ?", (data.port,)
        ).fetchone()
        if dup:
            raise HTTPException(
                status_code=409,
                detail={"code": 40301, "message": f"端口 {data.port} 已被实例\"{dup['name']}\"占用"},
            )
        inst_id = _new_id()
        conn.execute(
            "INSERT INTO mock_instances (id, name, topology_id, port, description, enabled, status) "
            "VALUES (?, ?, ?, ?, ?, ?, 'stopped')",
            (inst_id, data.name, data.topology_id, data.port, data.description, 1 if data.enabled else 0),
        )
    if data.enabled:
        _get_runner(request).start_instance(inst_id, data.port, data.topology_id)
    return {"code": 0, "data": {"id": inst_id}, "message": "ok"}


@router.put("/mock-instances/{inst_id}")
def update_mock_instance(inst_id: str, data: MockInstanceUpdate, request: Request) -> dict:
    with transaction() as conn:
        existing = conn.execute(
            "SELECT id FROM mock_instances WHERE id = ?", (inst_id,)
        ).fetchone()
        if not existing:
            raise HTTPException(
                status_code=404,
                detail={"code": 40401, "message": "实例不存在"},
            )
        if data.port is not None:
            dup = conn.execute(
                "SELECT id, name FROM mock_instances WHERE port = ? AND id != ?",
                (data.port, inst_id),
            ).fetchone()
            if dup:
                raise HTTPException(
                    status_code=409,
                    detail={"code": 40301, "message": f"端口 {data.port} 已被实例\"{dup['name']}\"占用"},
                )
        updates, params = [], []
        if data.name is not None:
            updates.append("name = ?"); params.append(data.name)
        if data.topology_id is not None:
            updates.append("topology_id = ?"); params.append(data.topology_id)
        if data.port is not None:
            updates.append("port = ?"); params.append(data.port)
        if data.description is not None:
            updates.append("description = ?"); params.append(data.description)
        if data.enabled is not None:
            updates.append("enabled = ?"); params.append(1 if data.enabled else 0)
        if updates:
            updates.append("updated_at = datetime('now')")
            params.append(inst_id)
            conn.execute(f"UPDATE mock_instances SET {', '.join(updates)} WHERE id = ?", params)
        # 读取更新后的配置，决定是否重启
        row = conn.execute(
            "SELECT port, topology_id, enabled FROM mock_instances WHERE id = ?", (inst_id,)
        ).fetchone()
    if row and row["enabled"]:
        _get_runner(request).restart_instance(inst_id, row["port"], row["topology_id"])
    else:
        _get_runner(request).stop_instance(inst_id)
    return {"code": 0, "data": {"id": inst_id}, "message": "ok"}


@router.delete("/mock-instances/{inst_id}")
def delete_mock_instance(inst_id: str, request: Request) -> dict:
    _get_runner(request).stop_instance(inst_id)
    with transaction() as conn:
        existing = conn.execute(
            "SELECT id FROM mock_instances WHERE id = ?", (inst_id,)
        ).fetchone()
        if not existing:
            raise HTTPException(
                status_code=404,
                detail={"code": 40401, "message": "实例不存在"},
            )
        conn.execute("DELETE FROM mock_instances WHERE id = ?", (inst_id,))
    return {"code": 0, "data": {"id": inst_id}, "message": "ok"}


@router.patch("/mock-instances/{inst_id}/enabled")
def patch_instance_enabled(inst_id: str, data: dict, request: Request) -> dict:
    enabled = data.get("enabled", True)
    with transaction() as conn:
        existing = conn.execute(
            "SELECT id FROM mock_instances WHERE id = ?", (inst_id,)
        ).fetchone()
        if not existing:
            raise HTTPException(
                status_code=404,
                detail={"code": 40401, "message": "实例不存在"},
            )
        conn.execute(
            "UPDATE mock_instances SET enabled = ?, updated_at = datetime('now') WHERE id = ?",
            (1 if enabled else 0, inst_id),
        )
        row = conn.execute(
            "SELECT port, topology_id FROM mock_instances WHERE id = ?", (inst_id,)
        ).fetchone()
    if row:
        if enabled:
            _get_runner(request).start_instance(inst_id, row["port"], row["topology_id"])
        else:
            _get_runner(request).stop_instance(inst_id)
    return {"code": 0, "data": {"id": inst_id}, "message": "ok"}


@router.get("/mock-instances/{inst_id}/logs")
def get_instance_logs(
    inst_id: str,
    limit: int = Query(default=100, ge=1, le=500),
    before: Optional[str] = Query(default=None),
) -> dict:
    with connect() as conn:
        inst = conn.execute("SELECT id FROM mock_instances WHERE id = ?", (inst_id,)).fetchone()
        if not inst:
            raise HTTPException(status_code=404, detail="实例不存在")

        conditions = ["instance_id = ?"]
        params: list = [inst_id]
        if before:
            conditions.append("ts < ?")
            params.append(before)
        where = " AND ".join(conditions)

        rows = conn.execute(
            f"SELECT * FROM request_logs WHERE {where} ORDER BY ts DESC LIMIT ?",
            params + [limit + 1],
        ).fetchall()

    has_more = len(rows) > limit
    items = [dict(r) for r in rows[:limit]]
    return {"code": 0, "data": {"items": items, "has_more": has_more}, "message": "ok"}


@router.delete("/mock-instances/{inst_id}/logs")
def clear_instance_logs(inst_id: str) -> dict:
    with connect() as conn:
        inst = conn.execute("SELECT id FROM mock_instances WHERE id = ?", (inst_id,)).fetchone()
        if not inst:
            raise HTTPException(status_code=404, detail="实例不存在")
        conn.execute("DELETE FROM request_logs WHERE instance_id = ?", (inst_id,))
    return {"code": 0, "data": {"id": inst_id}, "message": "ok"}
