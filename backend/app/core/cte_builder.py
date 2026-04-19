"""Dynamic CTE view generation for the SQL mode of API configs.

Runtime behavior (per docs/数据库表设计.md §5):
- Each node_type present in the topology becomes a CTE named after its `code`,
  with columns = fixed node columns + pivoted attrs from node_type_fields.
- Each edge_type present in the topology becomes a CTE named after its `code`,
  with source/target names and dn joined in, plus pivoted attrs.
- Generic CTEs `nodes` / `edges` / `children` are always emitted.
- The bound topology id is referenced via the `:__tid__` placeholder.
"""

import re
import sqlite3
from typing import Any

_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

NODE_FIXED_COLUMNS: list[str] = [
    "id",
    "name",
    "dn",
    "status",
    "created_at",
    "updated_at",
]

EDGE_FIXED_COLUMNS: list[str] = [
    "id",
    "source_id",
    "target_id",
    "status",
    "created_at",
    "updated_at",
]

EDGE_JOIN_COLUMNS: list[str] = [
    "source_name",
    "source_dn",
    "target_name",
    "target_dn",
]

GENERIC_VIEW_NAMES: list[str] = ["nodes", "edges", "children"]

_RESERVED_NAMES: set[str] = {"nodes", "edges", "children"}


def is_valid_ident(s: str) -> bool:
    """Whether `s` is a safe SQL identifier (no injection surface)."""
    return bool(s) and bool(_IDENT_RE.match(s))


def _fetch_used_node_types(conn: sqlite3.Connection, topology_id: str) -> list[dict]:
    rows = conn.execute(
        """
        SELECT DISTINCT nt.id, nt.code, nt.name
        FROM node_types nt
        JOIN nodes n ON n.node_type_id = nt.id
        WHERE n.topology_id = ?
        ORDER BY nt.code
        """,
        (topology_id,),
    ).fetchall()
    return [{"id": r["id"], "code": r["code"], "name": r["name"]} for r in rows]


def _fetch_used_edge_types(conn: sqlite3.Connection, topology_id: str) -> list[dict]:
    rows = conn.execute(
        """
        SELECT DISTINCT et.id, et.code, et.name
        FROM edge_types et
        JOIN edges e ON e.edge_type_id = et.id
        WHERE e.topology_id = ?
        ORDER BY et.code
        """,
        (topology_id,),
    ).fetchall()
    return [{"id": r["id"], "code": r["code"], "name": r["name"]} for r in rows]


def _fetch_node_fields(conn: sqlite3.Connection, node_type_id: str) -> list[str]:
    rows = conn.execute(
        """
        SELECT field_key FROM node_type_fields
        WHERE node_type_id = ?
        ORDER BY sort_order, id
        """,
        (node_type_id,),
    ).fetchall()
    return [r["field_key"] for r in rows if is_valid_ident(r["field_key"])]


def _fetch_edge_fields(conn: sqlite3.Connection, edge_type_id: str) -> list[str]:
    rows = conn.execute(
        """
        SELECT field_key FROM edge_type_fields
        WHERE edge_type_id = ?
        ORDER BY sort_order, id
        """,
        (edge_type_id,),
    ).fetchall()
    return [r["field_key"] for r in rows if is_valid_ident(r["field_key"])]


def build_node_type_cte(code: str, type_id: str, field_keys: list[str]) -> dict[str, Any]:
    """Return `{name, columns, sql}` for a node_type CTE.

    Emits SELECT body only (caller wraps with `WITH <name> AS (...)`).
    """
    columns = list(NODE_FIXED_COLUMNS)
    pivots: list[str] = []
    for key in field_keys:
        if key in columns:
            continue
        columns.append(key)
        pivots.append(f"MAX(CASE WHEN a.field_key = '{key}' THEN a.value END) AS {key}")

    fixed = [f"n.{c}" for c in NODE_FIXED_COLUMNS]
    select_lines = fixed + pivots
    select_body = ",\n         ".join(select_lines)

    # type_id is a generated string like `nt_switch` from seed; bind-safe as literal
    # since it comes from DB rows we just read.
    sql = (
        f"SELECT {select_body}\n"
        "  FROM nodes n\n"
        "  LEFT JOIN node_attrs a ON a.node_id = n.id\n"
        "  WHERE n.topology_id = :__tid__\n"
        f"    AND n.node_type_id = '{type_id}'\n"
        "  GROUP BY n.id"
    )
    return {"name": code, "columns": columns, "sql": sql}


def build_edge_type_cte(code: str, type_id: str, field_keys: list[str]) -> dict[str, Any]:
    columns = list(EDGE_FIXED_COLUMNS) + list(EDGE_JOIN_COLUMNS)
    pivots: list[str] = []
    for key in field_keys:
        if key in columns:
            continue
        columns.append(key)
        pivots.append(f"MAX(CASE WHEN a.field_key = '{key}' THEN a.value END) AS {key}")

    fixed = [f"e.{c}" for c in EDGE_FIXED_COLUMNS]
    joins = [
        "s.name AS source_name",
        "s.dn   AS source_dn",
        "t.name AS target_name",
        "t.dn   AS target_dn",
    ]
    select_body = ",\n         ".join(fixed + joins + pivots)
    sql = (
        f"SELECT {select_body}\n"
        "  FROM edges e\n"
        "  JOIN nodes s ON s.id = e.source_id\n"
        "  JOIN nodes t ON t.id = e.target_id\n"
        "  LEFT JOIN edge_attrs a ON a.edge_id = e.id\n"
        "  WHERE e.topology_id = :__tid__\n"
        f"    AND e.edge_type_id = '{type_id}'\n"
        "  GROUP BY e.id"
    )
    return {"name": code, "columns": columns, "sql": sql}


def build_generic_ctes() -> list[dict[str, Any]]:
    """Always-available CTEs: nodes / edges / children.

    Uses schema-qualified `main.nodes` / `main.edges` in bodies to bypass CTE
    name shadowing (SQLite otherwise reports circular reference).
    """
    nodes_sql = (
        "SELECT id, topology_id, node_type_id, name, dn, status,\n"
        "         created_at, updated_at\n"
        "  FROM main.nodes\n"
        "  WHERE topology_id = :__tid__"
    )
    edges_sql = (
        "SELECT id, topology_id, edge_type_id, source_id, target_id, status,\n"
        "         created_at, updated_at\n"
        "  FROM main.edges\n"
        "  WHERE topology_id = :__tid__"
    )
    children_sql = (
        "SELECT e.source_id AS parent_id,\n"
        "         n.id, n.name, n.dn, n.status, n.node_type_id\n"
        "  FROM main.edges e\n"
        "  JOIN main.edge_types et ON et.id = e.edge_type_id AND et.semantic = 'contain'\n"
        "  JOIN main.nodes n ON n.id = e.target_id\n"
        "  WHERE e.topology_id = :__tid__"
    )
    return [
        {
            "name": "nodes",
            "columns": [
                "id", "topology_id", "node_type_id", "name", "dn", "status",
                "created_at", "updated_at",
            ],
            "sql": nodes_sql,
        },
        {
            "name": "edges",
            "columns": [
                "id", "topology_id", "edge_type_id", "source_id", "target_id",
                "status", "created_at", "updated_at",
            ],
            "sql": edges_sql,
        },
        {
            "name": "children",
            "columns": [
                "parent_id", "id", "name", "dn", "status", "node_type_id",
            ],
            "sql": children_sql,
        },
    ]


def collect_views(
    conn: sqlite3.Connection, topology_id: str
) -> dict[str, list[dict[str, Any]]]:
    """Return node/edge/generic view metadata for a topology."""
    node_views: list[dict[str, Any]] = []
    for nt in _fetch_used_node_types(conn, topology_id):
        if not is_valid_ident(nt["code"]) or nt["code"] in _RESERVED_NAMES:
            continue
        fields = _fetch_node_fields(conn, nt["id"])
        node_views.append(build_node_type_cte(nt["code"], nt["id"], fields))

    edge_views: list[dict[str, Any]] = []
    existing_names = {v["name"] for v in node_views} | _RESERVED_NAMES
    for et in _fetch_used_edge_types(conn, topology_id):
        if not is_valid_ident(et["code"]) or et["code"] in existing_names:
            continue
        fields = _fetch_edge_fields(conn, et["id"])
        edge_views.append(build_edge_type_cte(et["code"], et["id"], fields))

    return {
        "nodeViews": node_views,
        "edgeViews": edge_views,
        "generic": build_generic_ctes(),
    }
