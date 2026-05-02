"""Response template renderer for API config test / mock endpoints.

Supported placeholders (per docs/开发方案.md §2.5):
    {{items}}        -> list returned by the SQL executor
    {{total}}        -> total row count
    {{page}}         -> current page number
    {{pageNo}}       -> alias for page (API doc uses pageNo)
    {{pageSize}}     -> page size
    {{totalPageNo}}  -> total pages, ceil(total/pageSize); 0 when pageSize<=0
    {{totalPages}}   -> alias for totalPageNo
    {{hasNext}}      -> bool, page < totalPageNo
    {{hasPrev}}      -> bool, page > 1 and total > 0
    {{offset}}       -> (page - 1) * pageSize
    {{count}}        -> len(items), actual rows on current page
    {{uuid}}         -> freshly generated uuid4 hex (with dashes)
    {{now}}          -> current UTC time, ISO-8601 seconds precision, ending with Z

Expressions (M6-02 LEGACY-05 Phase 2, per docs §2.12):
    Anything inside `{{ }}` that is not a bare identifier is treated as an
    arithmetic expression. Grammar (EBNF):
        expression  = term { ("+" | "-") term } ;
        term        = factor { ("*" | "/" | "%") factor } ;
        factor      = ("+" | "-") factor | primary ;
        primary     = NUMBER | IDENTIFIER | function_call | "(" expression ")" ;
    Function whitelist (7): ceil, floor, round, abs, min(2), max(2), int.
    Disabled: ** (Pow), // (FloorDiv), bit ops, comparisons, boolean ops,
    string/list/dict literals, lambdas, IfExp, attribute/subscript access.
    Resource caps: expression length ≤ 200 chars; AST nodes ≤ 50; |result| ≤ 1e15.
    All failures map to TemplateRenderError → HTTP 400 + code 40303.

Rules:
- The template is a nested structure (dict/list/primitive) already parsed from
  JSON at config time, OR a raw JSON string. When passed as a string we try
  `json.loads` first; if parsing fails we raise `TemplateRenderError` (→ 40303).
- A STRING that is *exactly* `"{{key}}"` is replaced by the raw value (so
  `"data": "{{items}}"` becomes `"data": [...]` — not `"data": "[...]"`).
- A string containing `{{key}}` as part of a longer string performs textual
  substitution — the value is stringified via `str(...)` (for scalars) or
  `json.dumps(..., ensure_ascii=False)` (for list/dict).
- Unknown bare-identifier placeholders pass through unchanged (so tokens in a
  real JSON body won't raise). Expressions instead raise on any error.
"""
from __future__ import annotations

import ast
import json
import math
import operator
import re
import uuid
from datetime import datetime
from typing import Any


class TemplateRenderError(ValueError):
    """Template rendering failed (malformed JSON, expression error, etc.)."""


# Non-greedy: matches `{{ <body> }}` with body containing any chars (no newlines).
# Body may be a bare identifier (legacy fast path) or an expression (Phase 2).
_PLACEHOLDER_RE = re.compile(r"\{\{\s*(.+?)\s*\}\}")
_IDENTIFIER_ONLY_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

# ---------------------------------------------------------------------------
# Expression engine (M6-02 LEGACY-05 Phase 2)
# ---------------------------------------------------------------------------

_EXPR_MAX_LEN = 200
_EXPR_MAX_NODES = 50
_EXPR_MAX_ABS = 10**15

_BINOP_TABLE: dict[type, Any] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Mod: operator.mod,
}

_UNARYOP_TABLE: dict[type, Any] = {
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
}

# Function whitelist: name -> (callable, expected_arity).
# arity is enforced strictly; min/max are 2-ary (no 3+ args).
_FUNC_TABLE: dict[str, tuple[Any, int]] = {
    "ceil": (math.ceil, 1),
    "floor": (math.floor, 1),
    "round": (round, 1),
    "abs": (abs, 1),
    "int": (int, 1),
    "min": (lambda a, b: min(a, b), 2),
    "max": (lambda a, b: max(a, b), 2),
}

# Allowed AST node types (exact match via type(node) in this set).
_ALLOWED_NODE_TYPES: frozenset[type] = frozenset({
    ast.Expression,
    ast.BinOp,
    ast.UnaryOp,
    ast.Constant,
    ast.Name,
    ast.Load,
    ast.Call,
    # Operator markers (children of BinOp/UnaryOp):
    ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Mod,
    ast.UAdd, ast.USub,
})


def _check_whitelist(tree: ast.AST) -> None:
    """Walk the AST and reject any node type outside the whitelist.

    Also enforces: Constant must be int|float (no bool/str/bytes/None);
    Name must be Load context; Call.func must be ast.Name with no kwargs/Starred.
    """
    nodes = list(ast.walk(tree))
    if len(nodes) > _EXPR_MAX_NODES:
        raise TemplateRenderError(
            f"表达式过于复杂 (>{_EXPR_MAX_NODES} nodes)"
        )
    for node in nodes:
        nt = type(node)
        if nt not in _ALLOWED_NODE_TYPES:
            raise TemplateRenderError(f"表达式禁用语法: {nt.__name__}")
        if nt is ast.Constant:
            v = node.value
            # bool is a subclass of int in Python; reject explicitly.
            if isinstance(v, bool) or not isinstance(v, (int, float)):
                raise TemplateRenderError(
                    f"表达式禁用字面量: {type(v).__name__}"
                )
        elif nt is ast.Name:
            if not isinstance(node.ctx, ast.Load):
                raise TemplateRenderError("表达式禁用语法: Name 非 Load 上下文")
        elif nt is ast.Call:
            if not isinstance(node.func, ast.Name):
                raise TemplateRenderError("表达式禁用语法: 非简单函数调用")
            if node.keywords:
                raise TemplateRenderError("表达式禁用语法: 关键字参数")
            for arg in node.args:
                if isinstance(arg, ast.Starred):
                    raise TemplateRenderError("表达式禁用语法: 星号展开")


def _eval_node(node: ast.AST, ctx: dict[str, Any]) -> Any:
    if isinstance(node, ast.Expression):
        return _eval_node(node.body, ctx)
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.Name):
        if node.id not in ctx:
            raise TemplateRenderError(f"表达式未定义变量: {node.id}")
        v = ctx[node.id]
        if isinstance(v, bool):
            return int(v)
        if not isinstance(v, (int, float)):
            raise TemplateRenderError(f"表达式变量 {node.id} 非数值")
        return v
    if isinstance(node, ast.BinOp):
        op = _BINOP_TABLE.get(type(node.op))
        if op is None:
            raise TemplateRenderError(
                f"表达式禁用运算符: {type(node.op).__name__}"
            )
        left = _eval_node(node.left, ctx)
        right = _eval_node(node.right, ctx)
        try:
            return op(left, right)
        except ZeroDivisionError:
            raise TemplateRenderError("表达式除零")
    if isinstance(node, ast.UnaryOp):
        op = _UNARYOP_TABLE.get(type(node.op))
        if op is None:
            raise TemplateRenderError(
                f"表达式禁用一元运算符: {type(node.op).__name__}"
            )
        return op(_eval_node(node.operand, ctx))
    if isinstance(node, ast.Call):
        # _check_whitelist 已确保 node.func 是 Name 且无 kwargs/Starred
        name = node.func.id
        entry = _FUNC_TABLE.get(name)
        if entry is None:
            raise TemplateRenderError(f"表达式未授权函数: {name}")
        fn, arity = entry
        if len(node.args) != arity:
            raise TemplateRenderError(
                f"表达式函数 {name} 参数数错: 应 {arity} 个，实 {len(node.args)} 个"
            )
        args = [_eval_node(a, ctx) for a in node.args]
        return fn(*args)
    # Should be unreachable due to _check_whitelist; defensive fallback.
    raise TemplateRenderError(f"表达式禁用节点: {type(node).__name__}")


def _eval_expression(expr: str, ctx: dict[str, Any]) -> Any:
    """Parse + whitelist + evaluate. All errors → TemplateRenderError."""
    if len(expr) > _EXPR_MAX_LEN:
        raise TemplateRenderError(
            f"表达式过长 (>{_EXPR_MAX_LEN} chars)"
        )
    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError as exc:
        raise TemplateRenderError(f"表达式语法错: {exc.msg}") from exc
    _check_whitelist(tree)
    result = _eval_node(tree, ctx)
    # Result must be numeric (int/float). bool is technically int-subclass but
    # would not arise: bool literals are rejected as Constant; Name returning
    # bool is auto-coerced to int in _eval_node. Defensive check anyway.
    if isinstance(result, bool) or not isinstance(result, (int, float)):
        raise TemplateRenderError(
            f"表达式结果类型错: {type(result).__name__}"
        )
    if math.isnan(result) or math.isinf(result):
        raise TemplateRenderError("表达式数值非有限")
    if abs(result) > _EXPR_MAX_ABS:
        raise TemplateRenderError(
            f"表达式数值溢出 (>{_EXPR_MAX_ABS:.0e})"
        )
    return result


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
    # Derived pagination vars (M6-01 LEGACY-05 Phase 1).
    # pageSize<=0 is defended even though _resolve_pagination clamps to ≥1,
    # because render_template is also called from static-mode rendering path
    # (request_pipeline._step6_render with page_size=0 when no SQL ran).
    total_page_no = math.ceil(total / page_size) if page_size > 0 else 0
    return {
        "items": items,
        "total": total,
        "page": page,
        "pageNo": page,
        "pageSize": page_size,
        "totalPageNo": total_page_no,
        "totalPages": total_page_no,
        "hasNext": page < total_page_no,
        "hasPrev": page > 1 and total > 0,
        "offset": (page - 1) * page_size if page_size > 0 else 0,
        "count": len(items),
        "uuid": str(uuid.uuid4()),  # with dashes, per docs §2.5
        "now": _now_iso(),
    }


def _render_str(s: str, ctx: dict[str, Any]) -> Any:
    """Render a single string value.

    Two dispatch paths inside each `{{ <body> }}`:
      1. Bare-identifier body → ctx lookup (legacy fast path).
         Unknown identifier passes through as literal `{{xxx}}`.
      2. Expression body → _eval_expression. Any error raises
         TemplateRenderError (no silent passthrough — user obviously
         expects evaluation when writing arithmetic).

    Outer modes (orthogonal):
      - Whole-string occupant (`"x": "{{...}}"`) → return raw value
        (preserves int/float/bool/list/dict types in JSON output).
      - In-string occupant (`"page {{x}} of {{y}}"`) → _stringify each.
    """
    stripped = s.strip()
    whole = _PLACEHOLDER_RE.fullmatch(stripped)
    if whole:
        body = whole.group(1).strip()
        if _IDENTIFIER_ONLY_RE.match(body):
            if body in ctx:
                return ctx[body]
            return s  # unknown bare identifier: passthrough literal
        # expression body — raises on error (caught by render_template caller)
        return _eval_expression(body, ctx)

    def _repl(m: re.Match) -> str:
        body = m.group(1).strip()
        if _IDENTIFIER_ONLY_RE.match(body):
            if body in ctx:
                return _stringify(ctx[body])
            return m.group(0)  # unknown bare identifier: passthrough literal
        return _stringify(_eval_expression(body, ctx))

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
