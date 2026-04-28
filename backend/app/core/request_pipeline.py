"""Six-step request pipeline for mock routes (M3-03).

Per docs §5.1 each mock request flows through six ordered steps:

  [1] route_match    — handled by FastAPI routing (outside this module)
  [2] check_enabled  — api_configs.enabled=false → 40404
  [3] authenticate   — config.auth type (none/xtoken/basic); M3-06
  [4] inject_fault   — config.inject delay/error; M3-05
  [5] execute        — SQL (execute_paged) or static (noop; body comes from step 6)
  [6] render         — template → body; or staticBody passthrough; or default

Each step may raise `PipelineError` to short-circuit with the documented error
code.
"""
from __future__ import annotations

import asyncio
import json
import random
import sqlite3
from dataclasses import dataclass
from typing import Any, Optional

from fastapi import Request
from fastapi.responses import JSONResponse, Response

from app.core.response_template import TemplateRenderError, render_template
from app.core.sql_executor import SqlValidationError, execute_paged
from app.db.connection import connect


class PipelineError(Exception):
    """Short-circuit signal carrying the HTTP status + business error code."""

    def __init__(self, http_status: int, code: int, message: str) -> None:
        self.http_status = http_status
        self.code = code
        self.message = message
        super().__init__(message)


class _RequestCtx:
    """Admin-helper-compatible shim (see `_lookup_source` in admin.api_config)."""

    __slots__ = ("headers", "query", "body", "path_params")

    def __init__(
        self,
        headers: dict[str, Any],
        query: dict[str, Any],
        body: Any,
        path_params: dict[str, Any],
    ) -> None:
        self.headers = headers
        self.query = query
        self.body = body
        self.path_params = path_params


@dataclass
class PipelineContext:
    api_id: str
    request: Request
    req_ctx: Optional[_RequestCtx] = None
    detail: Any = None
    exec_result: Optional[dict] = None
    body: Any = None
    status_code: int = 200
    content_type: str = "application/json"


async def _build_req_ctx(request: Request) -> _RequestCtx:
    body_json: Any = None
    if request.method in ("POST", "PUT", "PATCH"):
        raw = await request.body()
        if raw:
            try:
                body_json = json.loads(raw)
            except json.JSONDecodeError:
                body_json = None

    path_params = dict(request.path_params)
    query = dict(request.query_params)
    for k, v in path_params.items():
        query.setdefault(k, v)

    return _RequestCtx(
        headers=dict(request.headers),
        query=query,
        body=body_json,
        path_params=path_params,
    )


async def run(api_id: str, request: Request) -> Response:
    """Entry point called by the per-api handler closure in `mock.handler`."""
    # Lazy import breaks the cycle mock.handler ↔ admin.api_config ↔ pipeline.
    from app.admin.api_config import (
        _build_sql_params,
        _default_sql_template,
        _resolve_pagination,
        _row_to_detail,
    )

    ctx = PipelineContext(api_id=api_id, request=request)
    try:
        with connect() as conn:
            _step2_check_enabled(conn, ctx, _row_to_detail)
            _step3_authenticate(conn, ctx)
            await _step4_inject_fault(ctx)
            ctx.req_ctx = await _build_req_ctx(request)
            _step5_execute(conn, ctx, _build_sql_params, _resolve_pagination)
            _step6_render(ctx, _default_sql_template)
    except PipelineError as exc:
        return JSONResponse(
            status_code=exc.http_status,
            content={"code": exc.code, "message": exc.message},
        )

    return JSONResponse(
        status_code=ctx.status_code,
        content=ctx.body,
        media_type=ctx.content_type,
    )


# ---------- Step 2 ----------
def _step2_check_enabled(conn, ctx: PipelineContext, row_to_detail) -> None:
    row = conn.execute(
        "SELECT * FROM api_configs WHERE id = ?", (ctx.api_id,)
    ).fetchone()
    if not row or not bool(row["enabled"]):
        raise PipelineError(404, 40404, "not found")
    ctx.detail = row_to_detail(row)


# ---------- Step 3 ----------
def _step3_authenticate(conn, ctx: PipelineContext) -> None:
    """Authenticate request based on config.auth type (M3-06).

   三种模式：
      - none: 放行
      - xtoken: 从 header[config.auth.headerName] 取值，查 tokens 表
      - basic: 解析 Authorization: Basic，解码后查 tokens 表（token=username, meta.password=pwd）
    """
    cfg = ctx.detail.config if isinstance(ctx.detail.config, dict) else {}
    auth = cfg.get("auth")
    if not isinstance(auth, dict):
        return
    auth_type = str(auth.get("type") or "none").lower()
    if auth_type == "none":
        return

    if auth_type == "xtoken":
        header_name = auth.get("headerName", "X-Auth-Token")
        token = ctx.request.headers.get(header_name)
        if not token:
            raise PipelineError(401, 40401, "未提供认证令牌")
        _validate_xtoken(conn, token)

    elif auth_type == "basic":
        raw_auth = ctx.request.headers.get("Authorization", "")
        if not raw_auth.startswith("Basic "):
            raise PipelineError(401, 40404, "Basic 认证失败")
        try:
            decoded = _base64_decode(raw_auth[6:])
            if ":" not in decoded:
                raise PipelineError(401, 40404, "Basic 认证失败")
            username, password = decoded.split(":", 1)
        except Exception:
            raise PipelineError(401, 40404, "Basic 认证失败")
        _validate_basic(conn, username, password)

    else:
        raise PipelineError(401, 40401, f"auth type {auth_type!r} not supported")


def _validate_xtoken(conn, token: str) -> None:
    row = conn.execute(
        "SELECT revoked, expires_at FROM tokens WHERE token = ?",
        (token,),
    ).fetchone()
    if not row:
        raise PipelineError(401, 40401, "认证令牌无效")
    if bool(row["revoked"]):
        raise PipelineError(401, 40403, "认证令牌已撤销")
    # expires_at 格式: "2026-12-31T23:59:59Z"
    expires_at_str = row["expires_at"]
    if expires_at_str <= _now_utc():
        raise PipelineError(401, 40402, "认证令牌已过期")


def _validate_basic(conn, username: str, password: str) -> None:
    row = conn.execute(
        "SELECT revoked, expires_at, meta FROM tokens WHERE token = ?",
        (username,),
    ).fetchone()
    if not row:
        raise PipelineError(401, 40404, "Basic 认证失败")
    if bool(row["revoked"]):
        raise PipelineError(401, 40403, "认证令牌已撤销")
    expires_at_str = row["expires_at"]
    if expires_at_str <= _now_utc():
        raise PipelineError(401, 40402, "认证令牌已过期")
    # Password check: meta is JSON string, parse to get password
    import json
    meta_str = row["meta"] or "{}"
    try:
        meta = json.loads(meta_str)
    except Exception:
        meta = {}
    stored_pwd = meta.get("password", "")
    if stored_pwd != password:
        raise PipelineError(401, 40404, "Basic 认证失败")


def _now_utc() -> str:
    from datetime import datetime
    return datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")


def _base64_decode(s: str) -> str:
    import base64
    return base64.b64decode(s.encode()).decode()


# ---------- Step 4 ----------
async def _step4_inject_fault(ctx: PipelineContext) -> None:
    """Latency + probabilistic error injection (M3-05).

    Reads `config.fault.{delayMs, errorRate, errorStatus}`:
      - delayMs ≥ 0 → asyncio.sleep BEFORE the error decision so observed
        latency is honored regardless of whether the error fires.
      - errorRate ∈ (0, 1] → random.random() < rate ⇒ short-circuit with
        PipelineError; HTTP status from `errorStatus` (default 500).

    Missing/invalid fault block ⇒ no-op. Negative / non-numeric delayMs and
    errorRate are silently ignored (defensive: bad UI input shouldn't 500).
    """
    cfg = ctx.detail.config if isinstance(ctx.detail.config, dict) else {}
    fault = cfg.get("fault")
    if not isinstance(fault, dict):
        return

    delay_ms = fault.get("delayMs")
    if isinstance(delay_ms, (int, float)) and not isinstance(delay_ms, bool) and delay_ms > 0:
        await asyncio.sleep(delay_ms / 1000.0)

    error_rate = fault.get("errorRate")
    if (
        isinstance(error_rate, (int, float))
        and not isinstance(error_rate, bool)
        and error_rate > 0
        and random.random() < float(error_rate)
    ):
        raw_status = fault.get("errorStatus")
        try:
            http_status = int(raw_status) if raw_status is not None else 500
        except (TypeError, ValueError):
            http_status = 500
        if not 400 <= http_status <= 599:
            http_status = 500
        raise PipelineError(http_status, 50001, "故障注入：模拟错误")


# ---------- Step 5 ----------
def _step5_execute(conn, ctx: PipelineContext, build_params, resolve_page) -> None:
    detail = ctx.detail
    if detail.data_source == "sql":
        if not detail.topology_id:
            raise PipelineError(400, 40001, "接口未绑定拓扑")
        if not (detail.sql_text and detail.sql_text.strip()):
            raise PipelineError(400, 40001, "sqlText 为空")

        sql_params = build_params(detail.config, ctx.req_ctx)
        page, page_size = resolve_page(detail.config, ctx.req_ctx)
        try:
            ctx.exec_result = execute_paged(
                conn,
                detail.topology_id,
                detail.sql_text,
                sql_params,
                page,
                page_size,
            )
        except SqlValidationError as exc:
            raise PipelineError(400, 40303, str(exc))
        except sqlite3.Error as exc:
            raise PipelineError(400, 40302, f"SQL 执行失败: {exc}")
    # Static mode: nothing to do here; step 6 handles body resolution.


# ---------- Step 6 ----------
def _step6_render(ctx: PipelineContext, default_tpl) -> None:
    detail = ctx.detail
    cfg = detail.config if isinstance(detail.config, dict) else {}
    response_cfg = cfg.get("response") if isinstance(cfg.get("response"), dict) else {}
    ctx.status_code = int(response_cfg.get("statusCode") or 200)
    ctx.content_type = response_cfg.get("contentType") or "application/json"
    template = response_cfg.get("template")

    if detail.data_source == "sql":
        if template is None:
            template = default_tpl()
        try:
            ctx.body = render_template(
                template,
                items=ctx.exec_result["items"],
                total=ctx.exec_result["total"],
                page=ctx.exec_result["page"],
                page_size=ctx.exec_result["pageSize"],
            )
        except TemplateRenderError as exc:
            raise PipelineError(400, 40303, str(exc))
        return

    # Static-mode body resolution: staticBody wins, else template-with-empty,
    # else the {code:0, data:null} floor.
    if cfg.get("staticBody") is not None:
        ctx.body = cfg.get("staticBody")
    elif template is not None:
        try:
            ctx.body = render_template(
                template, items=[], total=0, page=1, page_size=0
            )
        except TemplateRenderError as exc:
            raise PipelineError(400, 40303, str(exc))
    else:
        ctx.body = {"code": 0, "data": None}
