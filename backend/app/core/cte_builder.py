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
    "group_id",
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
    "source_group_id",
    "target_name",
    "target_dn",
    "target_group_id",
]

GENERIC_VIEW_NAMES: list[str] = ["nodes", "edges", "children", "node_groups", "group_nodes", "group_edges", "topology_nodes", "topology_edges"]

_RESERVED_NAMES: set[str] = {"nodes", "edges", "children", "node_groups", "group_nodes", "group_edges", "topology_nodes", "topology_edges"}


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

    # `group_id` is a column on nodes but can be renamed by pivot — skip pivot for it
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
        "s.group_id AS source_group_id",
        "t.name AS target_name",
        "t.dn   AS target_dn",
        "t.group_id AS target_group_id",
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


def _build_group_nodes_cte() -> dict[str, Any]:
    """Virtual node generation from node_groups definitions via recursive CTE.

    No materialization required — generates rows on-the-fly from name_template
    and node_count.  Capped at 100 000 per group to prevent runaway recursion.
    """
    sql = (
        "WITH RECURSIVE\n"
        "gn_seq(grp_id, idx) AS (\n"
        "    SELECT id, 1 FROM main.node_groups\n"
        "     WHERE topology_id = :__tid__ AND node_count > 0\n"
        "    UNION ALL\n"
        "    SELECT s.grp_id, s.idx + 1\n"
        "    FROM gn_seq s\n"
        "    JOIN main.node_groups ng ON ng.id = s.grp_id\n"
        "    WHERE s.idx < ng.node_count AND s.idx < 100000\n"
        ")\n"
        "SELECT\n"
        "    ng.id || '_' || CAST(s.idx AS TEXT) AS id,\n"
        "    ng.topology_id,\n"
        "    ng.node_type_id,\n"
        "    CASE\n"
        "        WHEN INSTR(ng.name_template, '{i:') > 0 THEN\n"
        "            REPLACE(\n"
        "                SUBSTR(ng.name_template, 1, INSTR(ng.name_template, '{i:') - 1),\n"
        "                '{group}', ng.group_name\n"
        "            ) ||\n"
        "            SUBSTR('00000000000000000000', 1,\n"
        "                MAX(0, CAST(SUBSTR(ng.name_template, INSTR(ng.name_template, '{i:0') + 4,\n"
        "                    INSTR(SUBSTR(ng.name_template, INSTR(ng.name_template, '{i:0') + 4), 'd}') - 1) AS INTEGER)\n"
        "                    - LENGTH(CAST(s.idx AS TEXT)))) ||\n"
        "            CAST(s.idx AS TEXT) ||\n"
        "            SUBSTR(ng.name_template, INSTR(ng.name_template, 'd}') + 2)\n"
        "        ELSE REPLACE(ng.name_template, '{group}', ng.group_name)\n"
        "    END AS name,\n"
        "    ng.id AS group_id,\n"
        "    ng.group_name,\n"
        "    s.idx AS node_index,\n"
        "    'online' AS status,\n"
        "    NULL AS dn,\n"
        "    datetime('now') AS created_at,\n"
        "    datetime('now') AS updated_at\n"
        "FROM gn_seq s\n"
        "JOIN main.node_groups ng ON ng.id = s.grp_id"
    )
    return {
        "name": "group_nodes",
        "columns": [
            "id", "topology_id", "node_type_id", "name", "dn", "status",
            "group_id", "group_name", "node_index",
            "created_at", "updated_at",
        ],
        "sql": sql,
    }


def _build_group_edges_cte() -> dict[str, Any]:
    """Edge strategy metadata CTE — shows connection rules between groups.

    Returns one row per edge-strategy entry (not per individual edge).
    Users can multiply by node_count(s) to estimate total edge counts.
    Uses json_extract for SQLite < 3.38 compatibility (no ->> operator).
    """
    sql = (
        "SELECT\n"
        "    ng_src.id || '->' || json_extract(es.value, '$.target_group_id') AS id,\n"
        "    ng_src.topology_id,\n"
        "    (SELECT id FROM main.edge_types WHERE code = json_extract(es.value, '$.edge_type_code')) AS edge_type_id,\n"
        "    ng_src.id AS source_id,\n"
        "    ng_src.group_name AS source_name,\n"
        "    ng_src.id AS source_group_id,\n"
        "    json_extract(es.value, '$.target_group_id') AS target_id,\n"
        "    COALESCE(\n"
        "        (SELECT group_name FROM main.node_groups WHERE id = json_extract(es.value, '$.target_group_id')),\n"
        "        (SELECT name FROM main.nodes WHERE id = json_extract(es.value, '$.target_group_id'))\n"
        "    ) AS target_name,\n"
        "    json_extract(es.value, '$.target_group_id') AS target_group_id,\n"
        "    json_extract(es.value, '$.edge_type_code') AS edge_type_code,\n"
        "    json_extract(es.value, '$.mode') AS mode,\n"
        "    CAST(json_extract(es.value, '$.ratio_k') AS INTEGER) AS ratio_k,\n"
        "    ng_src.node_count AS source_node_count,\n"
        "    COALESCE(\n"
        "        (SELECT node_count FROM main.node_groups WHERE id = json_extract(es.value, '$.target_group_id')),\n"
        "        1\n"
        "    ) AS target_node_count\n"
        "FROM main.node_groups ng_src,\n"
        "     json_each(ng_src.edge_strategies) es\n"
        "WHERE ng_src.topology_id = :__tid__\n"
        "  AND ng_src.edge_strategies IS NOT NULL\n"
        "  AND ng_src.edge_strategies <> '[]'\n"
        "  AND ng_src.edge_strategies <> ''"
    )
    return {
        "name": "group_edges",
        "columns": [
            "id", "topology_id", "edge_type_id", "source_id", "source_name", "source_group_id",
            "target_id", "target_name", "target_group_id",
            "edge_type_code", "mode", "ratio_k",
            "source_node_count", "target_node_count",
        ],
        "sql": sql,
    }


def _build_topology_nodes_cte() -> dict[str, Any]:
    """Unified node view combining physical nodes and virtual group nodes.

    Single CTE for all nodes.  References the `group_nodes` CTE (defined
    earlier in the same WITH clause) for virtual group-node rows.
    Add `WHERE node_category = '...'` to filter.
    """
    sql = (
        # --- Physical nodes ---
        "SELECT\n"
        "    id,\n"
        "    topology_id,\n"
        "    node_type_id,\n"
        "    name,\n"
        "    dn,\n"
        "    status,\n"
        "    group_id,\n"
        "    'physical' AS node_category,\n"
        "    NULL AS group_name,\n"
        "    NULL AS node_index,\n"
        "    1 AS group_node_count,\n"
        "    created_at,\n"
        "    updated_at\n"
        "  FROM main.nodes\n"
        "  WHERE topology_id = :__tid__\n"
        "\n"
        "UNION ALL\n"
        "\n"
        # --- Virtual group nodes (from the already-defined group_nodes CTE) ---
        "SELECT\n"
        "    id,\n"
        "    topology_id,\n"
        "    node_type_id,\n"
        "    name,\n"
        "    dn,\n"
        "    status,\n"
        "    group_id,\n"
        "    'group_node' AS node_category,\n"
        "    group_name,\n"
        "    node_index,\n"
        "    (SELECT node_count FROM main.node_groups WHERE id = group_nodes.group_id) AS group_node_count,\n"
        "    created_at,\n"
        "    updated_at\n"
        "  FROM group_nodes"
    )
    return {
        "name": "topology_nodes",
        "columns": [
            "id", "topology_id", "node_type_id", "name", "dn", "status",
            "group_id",
            "node_category", "group_name", "node_index", "group_node_count",
            "created_at", "updated_at",
        ],
        "sql": sql,
    }


def _build_topology_edges_cte() -> dict[str, Any]:
    """Unified edge view combining physical edges, group strategies, and hybrid connections.

    Single CTE for all relationship types.  Add `WHERE edge_category = '...'` to filter.
    """
    sql = (
        # --- Physical edges ---
        "SELECT\n"
        "    e.id,\n"
        "    e.topology_id,\n"
        "    et.code AS edge_type_code,\n"
        "    e.source_id,\n"
        "    s.name AS source_name,\n"
        "    e.target_id,\n"
        "    t.name AS target_name,\n"
        "    s.group_id AS source_group_id,\n"
        "    t.group_id AS target_group_id,\n"
        "    e.status,\n"
        "    NULL AS mode,\n"
        "    NULL AS ratio_k,\n"
        "    1 AS source_node_count,\n"
        "    1 AS target_node_count,\n"
        "    'physical' AS edge_category,\n"
        "    e.created_at,\n"
        "    e.updated_at\n"
        "  FROM main.edges e\n"
        "  JOIN main.edge_types et ON et.id = e.edge_type_id\n"
        "  JOIN main.nodes s ON s.id = e.source_id\n"
        "  JOIN main.nodes t ON t.id = e.target_id\n"
        "  WHERE e.topology_id = :__tid__\n"
        "\n"
        "UNION ALL\n"
        "\n"
        # --- Group-to-group strategies ---
        "SELECT\n"
        "    ng_src.id || '->' || json_extract(es.value, '$.target_group_id') AS id,\n"
        "    ng_src.topology_id,\n"
        "    json_extract(es.value, '$.edge_type_code') AS edge_type_code,\n"
        "    ng_src.id AS source_id,\n"
        "    ng_src.group_name AS source_name,\n"
        "    json_extract(es.value, '$.target_group_id') AS target_id,\n"
        "    tgt_ng.group_name AS target_name,\n"
        "    ng_src.id AS source_group_id,\n"
        "    json_extract(es.value, '$.target_group_id') AS target_group_id,\n"
        "    'strategy' AS status,\n"
        "    json_extract(es.value, '$.mode') AS mode,\n"
        "    CAST(json_extract(es.value, '$.ratio_k') AS INTEGER) AS ratio_k,\n"
        "    ng_src.node_count AS source_node_count,\n"
        "    tgt_ng.node_count AS target_node_count,\n"
        "    'group_strategy' AS edge_category,\n"
        "    ng_src.created_at,\n"
        "    ng_src.updated_at\n"
        "  FROM main.node_groups ng_src,\n"
        "       json_each(ng_src.edge_strategies) es\n"
        "  JOIN main.node_groups tgt_ng ON tgt_ng.id = json_extract(es.value, '$.target_group_id')\n"
        "  WHERE ng_src.topology_id = :__tid__\n"
        "    AND ng_src.edge_strategies IS NOT NULL\n"
        "    AND ng_src.edge_strategies <> '[]'\n"
        "    AND ng_src.edge_strategies <> ''\n"
        "\n"
        "UNION ALL\n"
        "\n"
        # --- Hybrid strategies (target is a normal node, not a group) ---
        "SELECT\n"
        "    ng_src.id || '->' || json_extract(es.value, '$.target_group_id') AS id,\n"
        "    ng_src.topology_id,\n"
        "    json_extract(es.value, '$.edge_type_code') AS edge_type_code,\n"
        "    ng_src.id AS source_id,\n"
        "    ng_src.group_name AS source_name,\n"
        "    json_extract(es.value, '$.target_group_id') AS target_id,\n"
        "    tgt_node.name AS target_name,\n"
        "    ng_src.id AS source_group_id,\n"
        "    NULL AS target_group_id,\n"
        "    'strategy' AS status,\n"
        "    json_extract(es.value, '$.mode') AS mode,\n"
        "    CAST(json_extract(es.value, '$.ratio_k') AS INTEGER) AS ratio_k,\n"
        "    ng_src.node_count AS source_node_count,\n"
        "    1 AS target_node_count,\n"
        "    'hybrid' AS edge_category,\n"
        "    ng_src.created_at,\n"
        "    ng_src.updated_at\n"
        "  FROM main.node_groups ng_src,\n"
        "       json_each(ng_src.edge_strategies) es\n"
        "  JOIN main.nodes tgt_node ON tgt_node.id = json_extract(es.value, '$.target_group_id')\n"
        "  WHERE ng_src.topology_id = :__tid__\n"
        "    AND ng_src.edge_strategies IS NOT NULL\n"
        "    AND ng_src.edge_strategies <> '[]'\n"
        "    AND ng_src.edge_strategies <> ''\n"
        "    AND json_extract(es.value, '$.target_group_id') NOT IN (\n"
        "        SELECT id FROM main.node_groups WHERE topology_id = :__tid__\n"
        "    )"
    )
    return {
        "name": "topology_edges",
        "columns": [
            "id", "topology_id", "edge_type_code",
            "source_id", "source_name", "target_id", "target_name",
            "source_group_id", "target_group_id",
            "status", "mode", "ratio_k",
            "source_node_count", "target_node_count",
            "edge_category",
            "created_at", "updated_at",
        ],
        "sql": sql,
    }


def build_generic_ctes() -> list[dict[str, Any]]:
    """Always-available CTEs: nodes / edges / children / node_groups / group_nodes / group_edges / topology_edges.
    """
    nodes_sql = (
        "SELECT id, topology_id, node_type_id, name, dn, status, group_id,\n"
        "         created_at, updated_at\n"
        "  FROM main.nodes\n"
        "  WHERE topology_id = :__tid__"
    )
    edges_sql = (
        "SELECT e.id, e.topology_id, e.edge_type_id, e.source_id, e.target_id, e.status,\n"
        "         e.created_at, e.updated_at,\n"
        "         s.name AS source_name, s.dn AS source_dn, s.group_id AS source_group_id,\n"
        "         t.name AS target_name, t.dn AS target_dn, t.group_id AS target_group_id\n"
        "  FROM main.edges e\n"
        "  JOIN main.nodes s ON s.id = e.source_id\n"
        "  JOIN main.nodes t ON t.id = e.target_id\n"
        "  WHERE e.topology_id = :__tid__"
    )
    children_sql = (
        "SELECT e.source_id AS parent_id,\n"
        "         n.id, n.name, n.dn, n.status, n.node_type_id, n.group_id\n"
        "  FROM main.edges e\n"
        "  JOIN main.edge_types et ON et.id = e.edge_type_id AND et.semantic = 'contain'\n"
        "  JOIN main.nodes n ON n.id = e.target_id\n"
        "  WHERE e.topology_id = :__tid__"
    )
    node_groups_sql = (
        "SELECT id, topology_id, node_type_id, group_name, node_count,\n"
        "         name_template, attr_strategies, edge_strategies,\n"
        "         created_at, updated_at\n"
        "  FROM main.node_groups\n"
        "  WHERE topology_id = :__tid__"
    )
    return [
        {
            "name": "nodes",
            "columns": [
                "id", "topology_id", "node_type_id", "name", "dn", "status",
                "group_id", "created_at", "updated_at",
            ],
            "sql": nodes_sql,
        },
        {
            "name": "edges",
            "columns": [
                "id", "topology_id", "edge_type_id", "source_id", "target_id",
                "status", "created_at", "updated_at",
                "source_name", "source_dn", "source_group_id",
                "target_name", "target_dn", "target_group_id",
            ],
            "sql": edges_sql,
        },
        {
            "name": "children",
            "columns": [
                "parent_id", "id", "name", "dn", "status", "node_type_id", "group_id",
            ],
            "sql": children_sql,
        },
        {
            "name": "node_groups",
            "columns": [
                "id", "topology_id", "node_type_id", "group_name", "node_count",
                "name_template", "attr_strategies", "edge_strategies",
                "created_at", "updated_at",
            ],
            "sql": node_groups_sql,
        },
        _build_group_nodes_cte(),
        _build_group_edges_cte(),
        _build_topology_nodes_cte(),
        _build_topology_edges_cte(),
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
