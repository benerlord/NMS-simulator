"""Response template renderer for API config test / mock endpoints.

Supported placeholders (per docs/开发方案.md §2.5):
    {{items}}   -> list returned by the SQL executor
    {{total}}   -> total row count
    {{page}}    -> current page number
    {{pageNo}}  -> alias for page (API doc uses pageNo)
    {{pageSize}}-> page size
    {{uuid}}    -> freshly generated uuid4 hex (with dashes)
    {{now}}     -> current UTC time, ISO-8601 seconds precision, ending with Z

Rules:
- The template is a nested structure (dict/list/primitive) already parsed from
  JSON at config time, OR a raw JSON string. When passed as a string we try
  `json.loads` first; if parsing fails we raise `TemplateRenderError` (→ 40303).
- A STRING that is *exactly* `"{{key}}"` is replaced by the raw value (so
  `"data": "{{items}}"` becomes `"data": [...]` — not `"data": "[...]"`).
- A string containing `{{key}}` as part of a longer string performs textual
  substitution — the value is stringified via `str(...)` (for scalars) or
  `json.dumps(..., ensure_ascii=False)` (for list/dict).
- Unknown placeholders pass through unchanged (so tokens in a real JSON body
  won't raise).
"""
from __future__ import annotations

import json
import re
import uuid
from datetime import datetime
from typing import Any


class TemplateRenderError(ValueError):
    """Template rendering failed (malformed JSON, etc.)."""


_PLACEHOLDER_RE = re.compile(r"\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\}")


def _now_iso() -> str:
    return datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")


def _stringify(value: Any) -> str:
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return "null"
    return str(value)


def _build_context(
    items: list[Any],
    total: int,
    page: int,
    page_size: int,
) -> dict[str, Any]:
    return {
        "items": items,
        "total": total,
        "page": page,
        "pageNo": page,
        "pageSize": page_size,
        "uuid": str(uuid.uuid4()),  # with dashes, per docs §2.5
        "now": _now_iso(),
    }


def _render_str(s: str, ctx: dict[str, Any]) -> Any:
    """Render a single string value.

    Whole-string placeholder → raw value substitution.
    Otherwise → textual replacement of every `{{key}}` token.
    """
    stripped = s.strip()
    whole = _PLACEHOLDER_RE.fullmatch(stripped)
    if whole:
        key = whole.group(1)
        if key in ctx:
            return ctx[key]
        return s

    def _repl(m: re.Match) -> str:
        key = m.group(1)
        if key in ctx:
            return _stringify(ctx[key])
        return m.group(0)

    return _PLACEHOLDER_RE.sub(_repl, s)


def _render_node(node: Any, ctx: dict[str, Any]) -> Any:
    if isinstance(node, str):
        return _render_str(node, ctx)
    if isinstance(node, dict):
        return {k: _render_node(v, ctx) for k, v in node.items()}
    if isinstance(node, list):
        return [_render_node(v, ctx) for v in node]
    return node


def render_template(
    template: Any,
    items: list[Any],
    total: int,
    page: int,
    page_size: int,
) -> Any:
    """Render `template` against the paging context and return the value.

    `template` may be a dict/list/primitive already parsed from JSON, OR a
    raw JSON string. A raw string that fails `json.loads` raises
    `TemplateRenderError` (caller maps to 40303).
    """
    ctx = _build_context(items, total, page, page_size)

    if isinstance(template, str):
        try:
            parsed = json.loads(template)
        except json.JSONDecodeError as exc:
            raise TemplateRenderError(f"响应模板不是合法 JSON: {exc}") from exc
        return _render_node(parsed, ctx)

    return _render_node(template, ctx)
