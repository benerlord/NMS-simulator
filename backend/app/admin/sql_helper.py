import sqlite3

from fastapi import APIRouter, HTTPException, Query

from app.admin.schemas.sql_helper import SqlExecuteRequest, SqlPreviewRequest
from app.core.cte_builder import collect_views
from app.core.sql_executor import (
    SqlValidationError,
    execute_paged,
    preview as build_preview,
)
from app.db.connection import connect

router = APIRouter(prefix="/admin/api/sql", tags=["SQL 辅助"])


def _check_topology(conn: sqlite3.Connection, topology_id: str) -> None:
    row = conn.execute(
        "SELECT id FROM topologies WHERE id = ?", (topology_id,)
    ).fetchone()
    if not row:
        raise HTTPException(
            status_code=404,
            detail={
                "code": 40101,
                "message": "拓扑不存在",
                "details": {"topologyId": topology_id},
            },
        )


@router.get("/views")
def list_sql_views(topology_id: str = Query(..., alias="topologyId")) -> dict:
    with connect() as conn:
        _check_topology(conn, topology_id)
        views = collect_views(conn, topology_id)

    return {
        "code": 0,
        "data": {
            "nodeViews": views["nodeViews"],
            "edgeViews": views["edgeViews"],
            "generic": views["generic"],
        },
        "message": "ok",
    }


@router.post("/preview")
def preview_sql(body: SqlPreviewRequest) -> dict:
    with connect() as conn:
        _check_topology(conn, body.topology_id)
        try:
            result = build_preview(
                conn,
                body.topology_id,
                body.sql,
                body.params,
                body.page,
                body.page_size,
            )
        except SqlValidationError as exc:
            raise HTTPException(
                status_code=400,
                detail={"code": 40303, "message": str(exc)},
            )

    return {"code": 0, "data": result, "message": "ok"}


@router.post("/execute")
def execute_sql(body: SqlExecuteRequest) -> dict:
    with connect() as conn:
        _check_topology(conn, body.topology_id)
        try:
            result = execute_paged(
                conn,
                body.topology_id,
                body.sql,
                body.params,
                body.page,
                body.page_size,
            )
        except SqlValidationError as exc:
            raise HTTPException(
                status_code=400,
                detail={"code": 40303, "message": str(exc)},
            )
        except sqlite3.Error as exc:
            raise HTTPException(
                status_code=400,
                detail={"code": 40302, "message": f"SQL 执行失败: {exc}"},
            )

    return {"code": 0, "data": result, "message": "ok"}
