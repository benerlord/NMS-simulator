"""Read-only SQL executor with CTE assembly and safe parameter binding.

Pipeline:
1. `validate_readonly(sql)` — reject non-SELECT/WITH and multi-statement SQL
2. CTE prefix (M2-12 views) is prepended at top level
3. The user SQL is wrapped as a subquery to get total via COUNT(*) and to add
   LIMIT/OFFSET for paging — SQLite permits `WITH` inside a subquery, and the
   top-level CTEs remain visible inside the nested user query
"""
from __future__ import annotations

import re
import sqlite3
import time
from typing import Any, Optional

from app.core.cte_builder import collect_views

_COMMENT_LINE = re.compile(r"--[^\n]*")
_COMMENT_BLOCK = re.compile(r"/\*.*?\*/", re.DOTALL)

RESERVED_PARAMS: frozenset[str] = frozenset({"__tid__", "__limit__", "__offset__"})


class SqlValidationError(ValueError):
    """Raised when SQL is not SELECT/WITH or contains multiple statements."""


def _strip_comments(sql: str) -> str:
    return _COMMENT_BLOCK.sub("", _COMMENT_LINE.sub("", sql))


def validate_readonly(sql: str) -> None:
    """Reject non-SELECT/WITH or multi-statement SQL."""
    if not sql or not sql.strip():
        raise SqlValidationError("SQL 不得为空")
    cleaned = _strip_comments(sql).strip().rstrip(";").strip()
    if ";" in cleaned:
        raise SqlValidationError("不允许多语句")
    head = cleaned[:6].upper()
    if not (head.startswith("SELECT") or head.startswith("WITH")):
        raise SqlValidationError("仅允许 SELECT / WITH 查询")


def _build_cte_prefix(conn: sqlite3.Connection, topology_id: str) -> str:
    views = collect_views(conn, topology_id)
    all_views: list[dict[str, Any]] = (
        views["nodeViews"] + views["edgeViews"] + views["generic"]
    )
    if not all_views:
        return ""
    parts = [f"{v['name']} AS (\n{v['sql']}\n)" for v in all_views]
    return "WITH " + ",\n".join(parts)


def _clean_user_sql(user_sql: str) -> str:
    return _strip_comments(user_sql).strip().rstrip(";").strip()


def assemble_sql(
    conn: sqlite3.Connection, topology_id: str, user_sql: str
) -> str:
    """Return `<our CTEs> <user_sql>` for non-paginated inspection."""
    cleaned = _clean_user_sql(user_sql)
    cte_prefix = _build_cte_prefix(conn, topology_id)
    if not cte_prefix:
        return cleaned
    return f"{cte_prefix}\n{cleaned}"


def _build_paged_sqls(
    conn: sqlite3.Connection, topology_id: str, user_sql: str
) -> tuple[str, str]:
    """Build `(count_sql, page_sql)` by wrapping user SQL as a subquery."""
    cleaned = _clean_user_sql(user_sql)
    cte_prefix = _build_cte_prefix(conn, topology_id)
    prefix = f"{cte_prefix}\n" if cte_prefix else ""
    count_sql = f"{prefix}SELECT COUNT(*) FROM (\n{cleaned}\n) _t"
    page_sql = (
        f"{prefix}SELECT * FROM (\n{cleaned}\n) _t\n"
        "LIMIT :__limit__ OFFSET :__offset__"
    )
    return count_sql, page_sql


def _build_bound_params(
    topology_id: str, params: dict[str, Any] | None, page: int, page_size: int
) -> dict[str, Any]:
    bound: dict[str, Any] = {}
    if params:
        for k, v in params.items():
            if k in RESERVED_PARAMS:
                continue
            bound[k] = v
    bound["__tid__"] = topology_id
    bound["__limit__"] = page_size
    bound["__offset__"] = (page - 1) * page_size
    return bound


def execute_paged(
    conn: sqlite3.Connection,
    topology_id: str,
    user_sql: str,
    params: dict[str, Any] | None,
    page: int,
    page_size: int,
) -> dict[str, Any]:
    """Execute `user_sql` with pagination; return items/total/meta."""
    validate_readonly(user_sql)
    bound = _build_bound_params(topology_id, params, page, page_size)
    count_sql, page_sql = _build_paged_sqls(conn, topology_id, user_sql)

    started = time.perf_counter()
    total_row = conn.execute(count_sql, bound).fetchone()
    total = int(total_row[0]) if total_row else 0
    rows = conn.execute(page_sql, bound).fetchall()
    duration_ms = int((time.perf_counter() - started) * 1000)

    items = [dict(r) for r in rows]

    return {
        "items": items,
        "total": total,
        "page": page,
        "pageSize": page_size,
        "generatedSql": page_sql,
        "boundParams": bound,
        "durationMs": duration_ms,
    }


def preview(
    conn: sqlite3.Connection,
    topology_id: str,
    user_sql: str,
    params: dict[str, Any] | None,
    page: int,
    page_size: int,
) -> dict[str, Any]:
    """Same as execute_paged but does not run the SQL."""
    validate_readonly(user_sql)
    bound = _build_bound_params(topology_id, params, page, page_size)
    count_sql, page_sql = _build_paged_sqls(conn, topology_id, user_sql)
    return {
        "generatedSql": page_sql,
        "countSql": count_sql,
        "boundParams": bound,
    }
