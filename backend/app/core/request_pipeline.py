"""Six-step request pipeline for mock routes (M3-03).

Per docs §5.1 each mock request flows through these ordered steps:

  [1] route_match    — handled by FastAPI routing (outside this module)
  [2] check_enabled  — api_configs.enabled=false → 40404
  [3] authenticate   — config.auth type (none/xtoken/basic); M3-06
  [3.5] validate_request — config.request 声明（M5-01）：
        - headers required + expectValue（不做白名单）
        - query    required + 类型校验 + 严格白名单（未声明字段 → 40025）
        - body     required 校验
        缺省 config.request 时整段跳过 → M4 老接口零变化。
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
import time as _time
from dataclasses import dataclass
from typing import Any, Optional

from fastapi import Request
from fastapi.responses import JSONResponse, Response

from app.core.response_template import TemplateRenderError, render_template
from app.core.sql_executor import SqlValidationError, execute_paged
from app.db.connection import connect


def _cfg_get(cfg: dict, camel: str, *also: str) -> Any:
    """Read a config key that may be stored in camelCase or snake_case.

    The frontend's `snakeizeKeys` interceptor converts all keys in the request
    body (including the opaque `config` JSON blob) to snake_case, so keys like
    ``staticBody`` may be persisted as ``static_body``.  This helper checks the
    canonical camelCase form first, then the auto-derived snake_case variant,
    then any extra aliases passed via *also.  Returns None when no variant is
    present.
    """
    if camel in cfg:
        return cfg[camel]
    snake = "".join(
        "_" + c.lower() if c.isupper() else c for c in camel
    ).lstrip("_")
    if snake != camel and snake in cfg:
        return cfg[snake]
    for alt in also:
        if alt in cfg:
            return cfg[alt]
    return None


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


async def run(api_id: str, request: Request, instance_id: Optional[str] = None) -> Response:
    """Entry point called by the per-api handler closure in `mock.handler`."""
    from app.admin.api_config import (
        _build_sql_params,
        _default_sql_template,
        _resolve_pagination,
        _row_to_detail,
    )

    start_ts = _time.time()
    ctx = PipelineContext(api_id=api_id, request=request)
    error_message: Optional[str] = None
    try:
        with connect() as conn:
            _step2_check_enabled(conn, ctx, _row_to_detail)
            _step3_authenticate(conn, ctx)
            ctx.req_ctx = await _build_req_ctx(request)
            await _step3_5_validate_request(ctx)
            await _step4_inject_fault(ctx)
            _step5_execute(conn, ctx, _build_sql_params, _resolve_pagination)
            _step6_render(ctx, _default_sql_template)
    except PipelineError as exc:
        error_message = exc.message
        duration_ms = int((_time.time() - start_ts) * 1000)
        _log_request(api_id, request, exc.http_status, duration_ms, error_message, instance_id)
        return JSONResponse(
            status_code=exc.http_status,
            content={"code": exc.code, "message": exc.message},
        )

    duration_ms = int((_time.time() - start_ts) * 1000)
    _log_request(api_id, request, ctx.status_code, duration_ms, None, instance_id)
    return JSONResponse(
        status_code=ctx.status_code,
        content=ctx.body,
        media_type=ctx.content_type,
    )


def _log_request(
    api_id: str,
    request: Request,
    status_code: int,
    duration_ms: int,
    error_message: Optional[str],
    instance_id: Optional[str],
) -> None:
    """Write a request log entry and enforce the 10000-row rolling cap."""
    try:
        client_ip = request.client.host if request.client else None
        query_str = str(request.query_params) if request.query_params else None
        with connect() as conn:
            conn.execute(
                """INSERT INTO request_logs
                   (api_id, method, path, query, status_code, duration_ms, client_ip, error_message, instance_id)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (api_id, request.method, request.url.path, query_str,
                 status_code, duration_ms, client_ip, error_message, instance_id),
            )
            conn.execute(
                "DELETE FROM request_logs WHERE id NOT IN "
                "(SELECT id FROM request_logs ORDER BY ts DESC LIMIT 10000)"
            )
    except Exception:
        pass


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
        header_name = _cfg_get(auth, "headerName", "header_name") or "X-Auth-Token"
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


# ---------- Step 3.5 (M5-01) ----------
async def _step3_5_validate_request(ctx: PipelineContext) -> None:
    """请求契约校验：headers / query / body 三段（M5-01）。

    短路错误码（HTTP 400）：
        40020 缺少必填请求头
        40021 请求头值不匹配 expectValue
        40022 缺少必填 query 参数
        40023 query 参数类型错误
        40024 （预留 LEGACY-02：content-type 严格匹配）
        40025 严格模式下未声明的 query 参数
        40026 请求体必填但为空

    设计要点：
        - `config.request` 缺失 → 整段跳过（M4 老接口零变化）
        - headers **不**做白名单（HTTP 标准头会自动注入，强制白名单会使所有请求失败）
        - query 严格白名单仅在 `config.request` 显式包含 `query` 字段时启用：
              * 缺 query 字段 → 不做白名单（自由模式）
              * query=[]    → 严格模式，任何 query 参数都拒绝
              * query=[...] → 严格模式，仅声明的允许
          这样让用户在字段层级显式选择是否启用白名单。
        - body required=True 时 await request.body() 读取已缓存的 bytes（不会
          重复消费 stream，因为 starlette 的 Request 内部缓存 raw bytes）
    """
    cfg = ctx.detail.config if isinstance(ctx.detail.config, dict) else {}
    req_spec = cfg.get("request")
    if not isinstance(req_spec, dict):
        return

    # 1) headers：required + expectValue（不做白名单）
    headers_spec = req_spec.get("headers")
    if isinstance(headers_spec, list):
        for h in headers_spec:
            if not isinstance(h, dict):
                continue
            name = h.get("name")
            if not name or not isinstance(name, str):
                continue
            actual = ctx.request.headers.get(name)
            if h.get("required") and actual is None:
                raise PipelineError(400, 40020, f"缺少必填请求头 {name}")
            expect = _cfg_get(h, "expectValue", "expect_value")
            if expect and actual is not None and actual != expect:
                raise PipelineError(
                    400, 40021, f"请求头 {name} 不匹配预期值"
                )

    # 2) query：required + 类型 + 严格白名单（条件触发）
    if "query" in req_spec:
        query_spec = req_spec.get("query") or []
        if not isinstance(query_spec, list):
            query_spec = []
        declared_names: set[str] = set()
        for q in query_spec:
            if not isinstance(q, dict):
                continue
            name = q.get("name")
            if not name or not isinstance(name, str):
                continue
            declared_names.add(name)
            actual = ctx.request.query_params.get(name)
            if q.get("required") and actual is None:
                raise PipelineError(
                    400, 40022, f"缺少必填 query 参数 {name}"
                )
            if actual is not None:
                qtype = q.get("type", "string")
                if qtype != "string":
                    try:
                        _coerce_query(actual, qtype)
                    except ValueError:
                        raise PipelineError(
                            400, 40023,
                            f"query 参数 {name} 类型应为 {qtype}",
                        )
        # 严格白名单：未声明的 query key 全部拒绝
        for actual_name in ctx.request.query_params.keys():
            if actual_name not in declared_names:
                raise PipelineError(
                    400, 40025,
                    f"未声明的 query 参数: {actual_name}",
                )

    # 3) body：required 校验
    body_spec = req_spec.get("body")
    if isinstance(body_spec, dict) and body_spec.get("required"):
        raw = await ctx.request.body()
        if not raw or not raw.strip():
            raise PipelineError(400, 40026, "请求体不得为空")


def _coerce_query(raw: str, qtype: str) -> object:
    """把 query string 按声明类型解析。失败抛 ValueError 由调用方转 40023。"""
    if qtype == "int":
        return int(raw)
    if qtype == "bool":
        low = raw.strip().lower()
        if low in ("true", "1", "yes", "on"):
            return True
        if low in ("false", "0", "no", "off"):
            return False
        raise ValueError(f"invalid bool: {raw!r}")
    return raw  # string 默认


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

    delay_ms = _cfg_get(fault, "delayMs", "delay_ms")
    if isinstance(delay_ms, (int, float)) and not isinstance(delay_ms, bool) and delay_ms > 0:
        await asyncio.sleep(delay_ms / 1000.0)

    error_rate = _cfg_get(fault, "errorRate", "error_rate")
    if (
        isinstance(error_rate, (int, float))
        and not isinstance(error_rate, bool)
        and error_rate > 0
        and random.random() < float(error_rate)
    ):
        raw_status = _cfg_get(fault, "errorStatus", "error_status")
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
    ctx.status_code = int(_cfg_get(response_cfg, "statusCode", "status_code") or 200)
    ctx.content_type = (_cfg_get(response_cfg, "contentType", "content_type") or "application/json")
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
    static_body = _cfg_get(cfg, "staticBody", "static_body")
    if static_body is not None:
        ctx.body = static_body
    elif template is not None:
        try:
            ctx.body = render_template(
                template, items=[], total=0, page=1, page_size=0
            )
        except TemplateRenderError as exc:
            raise PipelineError(400, 40303, str(exc))
    else:
        ctx.body = {"code": 0, "data": None}
