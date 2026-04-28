import json
import sqlite3
import time
import uuid
from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query

from app.core.response_template import TemplateRenderError, render_template
from app.core.sql_executor import SqlValidationError, execute_paged
from app.db.connection import connect, transaction
from app.admin.schemas import (
    ApiConfigCreate,
    ApiConfigDetail,
    ApiConfigDetailResponse,
    ApiConfigEnabledPatch,
    ApiConfigItem,
    ApiConfigListResponse,
    ApiConfigTopologyPatch,
    ApiConfigUpdate,
    ApiTestRequest,
    ApiTestResponse,
    ApiTestResult,
)

router = APIRouter(prefix="/admin/api", tags=["接口配置"])


def _new_id() -> str:
    return f"api_{uuid.uuid4().hex[:12]}"


def _now() -> str:
    return datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_dt(val: Any) -> datetime:
    if isinstance(val, str):
        return datetime.fromisoformat(val.replace("Z", "+00:00"))
    return val


def _row_to_item(row) -> ApiConfigItem:
    return ApiConfigItem(
        id=row["id"],
        name=row["name"],
        method=row["method"],
        path=row["path"],
        enabled=bool(row["enabled"]),
        group_name=row["group_name"],
        data_source=row["data_source"],
        topology_id=row["topology_id"],
        created_at=_parse_dt(row["created_at"]),
        updated_at=_parse_dt(row["updated_at"]),
    )


def _row_to_detail(row) -> ApiConfigDetail:
    try:
        cfg = json.loads(row["config"]) if row["config"] else {}
    except json.JSONDecodeError:
        cfg = {}
    return ApiConfigDetail(
        id=row["id"],
        name=row["name"],
        method=row["method"],
        path=row["path"],
        enabled=bool(row["enabled"]),
        group_name=row["group_name"],
        data_source=row["data_source"],
        topology_id=row["topology_id"],
        sql_text=row["sql_text"],
        config=cfg if isinstance(cfg, dict) else {},
        created_at=_parse_dt(row["created_at"]),
        updated_at=_parse_dt(row["updated_at"]),
    )


def _ensure_topology(conn, topology_id: str) -> None:
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


def _ensure_api_exists(conn, api_id: str):
    row = conn.execute(
        "SELECT * FROM api_configs WHERE id = ?", (api_id,)
    ).fetchone()
    if not row:
        raise HTTPException(
            status_code=404,
            detail={
                "code": 40301,
                "message": "接口配置不存在",
                "details": {"apiId": api_id},
            },
        )
    return row


# GET /admin/api/apis
@router.get("/apis", response_model=ApiConfigListResponse)
def list_apis(
    group_name: Optional[str] = Query(None, alias="groupName"),
    enabled: Optional[bool] = Query(None),
    topology_id: Optional[str] = Query(None, alias="topologyId"),
    method: Optional[str] = Query(None),
    path: Optional[str] = Query(None, description="path 模糊匹配"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=500, alias="pageSize"),
) -> dict:
    conditions: list[str] = []
    params: list[Any] = []
    if group_name is not None:
        conditions.append("group_name = ?")
        params.append(group_name)
    if enabled is not None:
        conditions.append("enabled = ?")
        params.append(1 if enabled else 0)
    if topology_id is not None:
        conditions.append("topology_id = ?")
        params.append(topology_id)
    if method is not None:
        conditions.append("method = ?")
        params.append(method.upper())
    if path is not None:
        conditions.append("path LIKE ?")
        params.append(f"%{path}%")

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    offset = (page - 1) * page_size

    with connect() as conn:
        total = conn.execute(
            f"SELECT COUNT(*) FROM api_configs {where}", params
        ).fetchone()[0]
        rows = conn.execute(
            f"""
            SELECT * FROM api_configs {where}
            ORDER BY updated_at DESC
            LIMIT ? OFFSET ?
            """,
            params + [page_size, offset],
        ).fetchall()

    items = [_row_to_item(r) for r in rows]
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


# GET /admin/api/apis/{api_id}
@router.get("/apis/{api_id}", response_model=ApiConfigDetailResponse)
def get_api(api_id: str) -> dict:
    with connect() as conn:
        row = _ensure_api_exists(conn, api_id)
        detail = _row_to_detail(row)
    return {"code": 0, "data": detail.model_dump(mode="json", by_alias=True), "message": "ok"}


# POST /admin/api/apis
@router.post("/apis", response_model=ApiConfigDetailResponse)
def create_api(body: ApiConfigCreate) -> dict:
    api_id = _new_id()
    now = _now()

    with transaction() as conn:
        dup = conn.execute(
            "SELECT id FROM api_configs WHERE method = ? AND path = ?",
            (body.method, body.path),
        ).fetchone()
        if dup:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": 40301,
                    "message": "接口路径已存在",
                    "details": {"method": body.method, "path": body.path},
                },
            )

        if "?" in (body.path or ""):
            raise HTTPException(
                status_code=400,
                detail={
                    "code": 40001,
                    "message": "路径不能包含 ? 字符，查询参数应作为独立 query string 传递",
                    "details": {"field": "path"},
                },
            )

        if body.topology_id:
            _ensure_topology(conn, body.topology_id)

        if body.data_source == "sql" and not (body.sql_text and body.sql_text.strip()):
            raise HTTPException(
                status_code=400,
                detail={
                    "code": 40001,
                    "message": "sqlText 不得为空",
                    "details": {"field": "sqlText"},
                },
            )

        conn.execute(
            """
            INSERT INTO api_configs
              (id, name, method, path, enabled, group_name, data_source,
               topology_id, sql_text, config, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                api_id,
                body.name,
                body.method,
                body.path,
                1 if body.enabled else 0,
                body.group_name,
                body.data_source,
                body.topology_id,
                body.sql_text,
                json.dumps(body.config or {}, ensure_ascii=False),
                now,
                now,
            ),
        )
        row = conn.execute(
            "SELECT * FROM api_configs WHERE id = ?", (api_id,)
        ).fetchone()
        detail = _row_to_detail(row)

    from app.mock.registry import registry as mock_registry
    mock_registry.register(detail.id, detail.method, detail.path)

    return {"code": 0, "data": detail.model_dump(mode="json", by_alias=True), "message": "ok"}


# PUT /admin/api/apis/{api_id}
@router.put("/apis/{api_id}", response_model=ApiConfigDetailResponse)
def update_api(api_id: str, body: ApiConfigUpdate) -> dict:
    updates: list[str] = []
    params: list[Any] = []

    if body.name is not None:
        updates.append("name = ?")
        params.append(body.name)
    if body.method is not None:
        updates.append("method = ?")
        params.append(body.method)
    if body.path is not None:
        if "?" in body.path:
            raise HTTPException(
                status_code=400,
                detail={
                    "code": 40001,
                    "message": "路径不能包含 ? 字符，查询参数应作为独立 query string 传递",
                    "details": {"field": "path"},
                },
            )
        updates.append("path = ?")
        params.append(body.path)
    if body.group_name is not None:
        updates.append("group_name = ?")
        params.append(body.group_name)
    if body.data_source is not None:
        updates.append("data_source = ?")
        params.append(body.data_source)
    if body.sql_text is not None:
        updates.append("sql_text = ?")
        params.append(body.sql_text)
    if body.config is not None:
        updates.append("config = ?")
        params.append(json.dumps(body.config, ensure_ascii=False))

    if not updates:
        raise HTTPException(
            status_code=400,
            detail={"code": 40001, "message": "无更新字段", "details": []},
        )

    with transaction() as conn:
        existing = _ensure_api_exists(conn, api_id)

        new_method = body.method if body.method is not None else existing["method"]
        new_path = body.path if body.path is not None else existing["path"]
        if body.method is not None or body.path is not None:
            dup = conn.execute(
                """
                SELECT id FROM api_configs
                WHERE method = ? AND path = ? AND id != ?
                """,
                (new_method, new_path, api_id),
            ).fetchone()
            if dup:
                raise HTTPException(
                    status_code=409,
                    detail={
                        "code": 40301,
                        "message": "接口路径已存在",
                        "details": {"method": new_method, "path": new_path},
                    },
                )

        updates.append("updated_at = ?")
        params.append(_now())
        params.append(api_id)

        conn.execute(
            f"UPDATE api_configs SET {', '.join(updates)} WHERE id = ?",
            params,
        )
        row = conn.execute(
            "SELECT * FROM api_configs WHERE id = ?", (api_id,)
        ).fetchone()
        detail = _row_to_detail(row)
        route_changed = body.method is not None or body.path is not None

    if route_changed:
        from app.mock.registry import registry as mock_registry
        mock_registry.update(detail.id, detail.method, detail.path)

    return {"code": 0, "data": detail.model_dump(mode="json", by_alias=True), "message": "ok"}


# PATCH /admin/api/apis/{api_id}/enabled
@router.patch("/apis/{api_id}/enabled", response_model=ApiConfigDetailResponse)
def patch_api_enabled(api_id: str, body: ApiConfigEnabledPatch) -> dict:
    with transaction() as conn:
        _ensure_api_exists(conn, api_id)
        conn.execute(
            "UPDATE api_configs SET enabled = ?, updated_at = ? WHERE id = ?",
            (1 if body.enabled else 0, _now(), api_id),
        )
        row = conn.execute(
            "SELECT * FROM api_configs WHERE id = ?", (api_id,)
        ).fetchone()
        detail = _row_to_detail(row)

    return {"code": 0, "data": detail.model_dump(mode="json", by_alias=True), "message": "ok"}


# PATCH /admin/api/apis/{api_id}/topology
@router.patch("/apis/{api_id}/topology", response_model=ApiConfigDetailResponse)
def patch_api_topology(api_id: str, body: ApiConfigTopologyPatch) -> dict:
    with transaction() as conn:
        _ensure_api_exists(conn, api_id)
        if body.topology_id:
            _ensure_topology(conn, body.topology_id)
        conn.execute(
            "UPDATE api_configs SET topology_id = ?, updated_at = ? WHERE id = ?",
            (body.topology_id, _now(), api_id),
        )
        row = conn.execute(
            "SELECT * FROM api_configs WHERE id = ?", (api_id,)
        ).fetchone()
        detail = _row_to_detail(row)

    return {"code": 0, "data": detail.model_dump(mode="json", by_alias=True), "message": "ok"}


# DELETE /admin/api/apis/{api_id}
@router.delete("/apis/{api_id}")
def delete_api(api_id: str) -> dict:
    with transaction() as conn:
        _ensure_api_exists(conn, api_id)
        conn.execute("DELETE FROM api_configs WHERE id = ?", (api_id,))

    from app.mock.registry import registry as mock_registry
    mock_registry.unregister(api_id)

    return {"code": 0, "data": {"id": api_id}, "message": "删除成功"}


# ---------- M2-14 测试执行 -------------------------------------------------


def _coerce(value: Any, type_hint: Optional[str]) -> Any:
    """Best-effort coerce query string values into declared param types."""
    if value is None or type_hint is None:
        return value
    try:
        if type_hint == "int":
            if isinstance(value, bool):
                return int(value)
            return int(value)
        if type_hint in ("bool", "boolean"):
            if isinstance(value, bool):
                return value
            if isinstance(value, str):
                return value.strip().lower() in ("1", "true", "yes", "y")
            return bool(value)
        return str(value)
    except (ValueError, TypeError):
        return value


def _resolve_bind_key(entry: dict[str, Any]) -> Optional[str]:
    raw = entry.get("bindTo") or entry.get("sqlParam") or entry.get("bind_to")
    if not raw:
        raw = entry.get("name") or entry.get("param")
    if not raw:
        return None
    return str(raw).lstrip(":")


def _lookup_source(entry: dict[str, Any], req: ApiTestRequest) -> Any:
    key = entry.get("name") or entry.get("param")
    if not key:
        return None
    location = (entry.get("in") or "query").lower()
    if location == "header":
        # HTTP headers are case-insensitive; lowercase compare
        for k, v in (req.headers or {}).items():
            if str(k).lower() == str(key).lower():
                return v
        return None
    if location == "body":
        if isinstance(req.body, dict):
            return req.body.get(key)
        return None
    if location == "path":
        path_params = getattr(req, "path_params", None) or {}
        return path_params.get(key)
    return (req.query or {}).get(key)


def _build_sql_params(
    config: dict[str, Any], req: ApiTestRequest
) -> dict[str, Any]:
    """Map configured params (M2-11 contract or doc contract) to SQL bind dict."""
    raw_params = config.get("params") or []
    bound: dict[str, Any] = {}
    for entry in raw_params:
        if not isinstance(entry, dict):
            continue
        bind_key = _resolve_bind_key(entry)
        if not bind_key:
            continue
        value = _lookup_source(entry, req)
        if value is None:
            value = entry.get("default")
        bound[bind_key] = _coerce(value, entry.get("type"))
    return bound


def _resolve_pagination(
    config: dict[str, Any], req: ApiTestRequest
) -> tuple[int, int]:
    """Return (page, page_size) from request query + pagination config defaults."""
    pg = config.get("pagination") if isinstance(config.get("pagination"), dict) else {}
    page_no_param = pg.get("pageNoParam") or "pageNo"
    page_size_param = pg.get("pageSizeParam") or "pageSize"
    default_page_size = pg.get("defaultPageSize") or 50

    query = req.query or {}
    raw_page = query.get(page_no_param) or query.get("page") or 1
    raw_size = query.get(page_size_param) or default_page_size

    try:
        page = max(1, int(raw_page))
    except (ValueError, TypeError):
        page = 1
    try:
        page_size = int(raw_size)
    except (ValueError, TypeError):
        page_size = int(default_page_size)
    page_size = max(1, min(page_size, 1000))
    return page, page_size


def _default_sql_template() -> dict[str, Any]:
    return {
        "code": 0,
        "data": "{{items}}",
        "total": "{{total}}",
        "pageNo": "{{pageNo}}",
        "pageSize": "{{pageSize}}",
    }


def _run_sql_test(
    conn: sqlite3.Connection, detail: ApiConfigDetail, req: ApiTestRequest
) -> ApiTestResult:
    if not detail.topology_id:
        raise HTTPException(
            status_code=400,
            detail={"code": 40001, "message": "接口未绑定拓扑，无法执行 SQL 测试"},
        )
    if not (detail.sql_text and detail.sql_text.strip()):
        raise HTTPException(
            status_code=400,
            detail={"code": 40001, "message": "sqlText 不得为空"},
        )

    sql_params = _build_sql_params(detail.config, req)
    page, page_size = _resolve_pagination(detail.config, req)

    started = time.perf_counter()
    try:
        exec_result = execute_paged(
            conn, detail.topology_id, detail.sql_text, sql_params, page, page_size
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

    response_cfg = detail.config.get("response") if isinstance(detail.config, dict) else None
    response_cfg = response_cfg if isinstance(response_cfg, dict) else {}
    status_code = int(response_cfg.get("statusCode") or 200)
    content_type = response_cfg.get("contentType") or "application/json"
    template = response_cfg.get("template")
    if template is None:
        template = _default_sql_template()

    try:
        body = render_template(
            template,
            items=exec_result["items"],
            total=exec_result["total"],
            page=exec_result["page"],
            page_size=exec_result["pageSize"],
        )
    except TemplateRenderError as exc:
        raise HTTPException(
            status_code=400,
            detail={"code": 40303, "message": str(exc)},
        )

    duration_ms = int((time.perf_counter() - started) * 1000)
    return ApiTestResult(
        status_code=status_code,
        headers={"Content-Type": content_type},
        body=body,
        duration_ms=duration_ms,
        generated_sql=exec_result["generatedSql"],
        bound_params=exec_result["boundParams"],
    )


def _run_static_test(detail: ApiConfigDetail) -> ApiTestResult:
    cfg = detail.config if isinstance(detail.config, dict) else {}
    response_cfg = cfg.get("response") if isinstance(cfg.get("response"), dict) else {}
    status_code = int(response_cfg.get("statusCode") or 200)
    content_type = response_cfg.get("contentType") or "application/json"

    body: Any
    if cfg.get("staticBody") is not None:
        body = cfg.get("staticBody")
    elif response_cfg.get("template") is not None:
        try:
            body = render_template(
                response_cfg["template"], items=[], total=0, page=1, page_size=0
            )
        except TemplateRenderError as exc:
            raise HTTPException(
                status_code=400,
                detail={"code": 40303, "message": str(exc)},
            )
    else:
        body = {"code": 0, "data": None}

    return ApiTestResult(
        status_code=status_code,
        headers={"Content-Type": content_type},
        body=body,
        duration_ms=0,
        generated_sql=None,
        bound_params={},
    )


# POST /admin/api/apis/{api_id}/test
@router.post("/apis/{api_id}/test", response_model=ApiTestResponse)
def test_api(api_id: str, body: ApiTestRequest) -> dict:
    with connect() as conn:
        row = _ensure_api_exists(conn, api_id)
        detail = _row_to_detail(row)
        if detail.data_source == "sql":
            result = _run_sql_test(conn, detail, body)
        else:
            result = _run_static_test(detail)

    return {
        "code": 0,
        "data": result.model_dump(mode="json", by_alias=True),
        "message": "ok",
    }
